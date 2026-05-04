import json
import random
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch import nn
from torch.optim import Adam
from torch.utils.data import DataLoader

from inframatch.cv.dataset import (
    CLASS_TO_IDX,
    CrackDataset,
    create_splits,
    eval_transforms,
    train_transforms,
)
from inframatch.cv.model import build_model, save_checkpoint


def get_device(require_cuda: bool = False):
    if torch.cuda.is_available():
        return "cuda"

    if require_cuda:
        raise RuntimeError(
            "CUDA was required but is not available. "
            "Your current PyTorch install cannot see the GPU."
        )

    return "cpu"


def describe_device(device: str) -> str:
    if device != "cuda":
        return "CPU"

    device_index = torch.cuda.current_device()
    name = torch.cuda.get_device_name(device_index)
    props = torch.cuda.get_device_properties(device_index)
    total_vram_gb = props.total_memory / (1024 ** 3)
    return f"CUDA:{device_index} ({name}, {total_vram_gb:.1f} GB VRAM)"


def format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def set_seed(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def ensure_splits(
    data_dir: str | Path = "data/sdnet",
    splits_dir: str | Path = "data/sdnet_splits",
    seed: int = 42,
):
    splits_dir = Path(splits_dir)
    required = [
        splits_dir / "train.csv",
        splits_dir / "val.csv",
        splits_dir / "test.csv",
    ]

    if all(path.exists() for path in required):
        return

    create_splits(data_dir=data_dir, output_dir=splits_dir, seed=seed)


def make_class_weights(dataset: CrackDataset):
    counts = dataset.df["label"].value_counts().sort_index()
    weights = len(dataset.df) / (len(counts) * counts)
    return torch.tensor(weights.tolist(), dtype=torch.float32)


def run_eval_epoch(model, loader, criterion, device: str):
    model.eval()

    running_loss = 0.0
    correct = 0
    total = 0
    preds_all = []
    labels_all = []

    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)

            logits = model(images)
            loss = criterion(logits, labels)

            preds = torch.argmax(logits, dim=1)

            batch_size = labels.size(0)
            running_loss += loss.item() * batch_size
            correct += (preds == labels).sum().item()
            total += batch_size

            preds_all.extend(preds.cpu().tolist())
            labels_all.extend(labels.cpu().tolist())

    avg_loss = running_loss / max(total, 1)
    accuracy = correct / max(total, 1)
    f1 = f1_score(labels_all, preds_all, zero_division=0) if labels_all else 0.0

    return {
        "loss": avg_loss,
        "accuracy": accuracy,
        "f1": f1,
    }


def train_model(
    data_dir: str | Path = "data/sdnet",
    splits_dir: str | Path = "data/sdnet_splits",
    model_path: str | Path = "models/crack_resnet18.pt",
    history_path: str | Path | None = None,
    batch_size: int = 32,
    epochs: int = 5,
    learning_rate: float = 1e-4,
    weight_decay: float = 1e-4,
    patience: int = 3,
    seed: int = 42,
    pretrained: bool = True,
    require_cuda: bool = False,
):
    set_seed(seed)
    ensure_splits(data_dir=data_dir, splits_dir=splits_dir, seed=seed)

    splits_dir = Path(splits_dir)
    model_path = Path(model_path)

    if history_path is None:
        history_path = model_path.with_name(f"{model_path.stem}_history.json")
    history_path = Path(history_path)

    device = get_device(require_cuda=require_cuda)
    pin_memory = device == "cuda"

    train_dataset = CrackDataset(splits_dir / "train.csv", transform=train_transforms())
    val_dataset = CrackDataset(splits_dir / "val.csv", transform=eval_transforms())

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
        pin_memory=pin_memory,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=pin_memory,
    )

    model = build_model(pretrained=pretrained).to(device)

    if device == "cuda":
        torch.backends.cudnn.benchmark = True

    class_weights = make_class_weights(train_dataset).to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = Adam(model.parameters(), lr=learning_rate, weight_decay=weight_decay)

    history = []
    best_val_f1 = -1.0
    best_epoch = 0
    stale_epochs = 0
    train_start_time = time.perf_counter()

    print(
        f"Training on {describe_device(device)} | "
        f"train_samples={len(train_dataset)} val_samples={len(val_dataset)} | "
        f"train_batches={len(train_loader)} val_batches={len(val_loader)}"
    )

    for epoch in range(1, epochs + 1):
        epoch_start_time = time.perf_counter()
        model.train()

        running_loss = 0.0
        correct = 0
        total = 0

        for images, labels in train_loader:
            images = images.to(device)
            labels = labels.to(device)

            optimizer.zero_grad()

            logits = model(images)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()

            preds = torch.argmax(logits, dim=1)

            batch_size_current = labels.size(0)
            running_loss += loss.item() * batch_size_current
            correct += (preds == labels).sum().item()
            total += batch_size_current

        train_loss = running_loss / max(total, 1)
        train_accuracy = correct / max(total, 1)
        val_metrics = run_eval_epoch(model, val_loader, criterion, device)

        epoch_result = {
            "epoch": epoch,
            "train_loss": train_loss,
            "train_accuracy": train_accuracy,
            "val_loss": val_metrics["loss"],
            "val_accuracy": val_metrics["accuracy"],
            "val_f1": val_metrics["f1"],
        }
        history.append(epoch_result)

        epoch_seconds = time.perf_counter() - epoch_start_time
        total_elapsed_seconds = time.perf_counter() - train_start_time
        average_epoch_seconds = total_elapsed_seconds / epoch
        eta_seconds = average_epoch_seconds * (epochs - epoch)
        epoch_result["epoch_seconds"] = round(epoch_seconds, 2)
        epoch_result["elapsed_seconds"] = round(total_elapsed_seconds, 2)
        epoch_result["eta_seconds"] = round(eta_seconds, 2)

        print(
            f"Epoch {epoch}/{epochs} | "
            f"train_loss={train_loss:.4f} train_acc={train_accuracy:.4f} | "
            f"val_loss={val_metrics['loss']:.4f} val_acc={val_metrics['accuracy']:.4f} "
            f"val_f1={val_metrics['f1']:.4f} | "
            f"epoch_time={format_duration(epoch_seconds)} "
            f"elapsed={format_duration(total_elapsed_seconds)} "
            f"eta={format_duration(eta_seconds)}"
        )

        if val_metrics["f1"] > best_val_f1:
            best_val_f1 = val_metrics["f1"]
            best_epoch = epoch
            stale_epochs = 0

            save_checkpoint(
                model,
                model_path,
                class_to_idx=CLASS_TO_IDX,
                metadata={
                    "best_epoch": best_epoch,
                    "best_val_f1": best_val_f1,
                    "seed": seed,
                },
            )
        else:
            stale_epochs += 1

        if patience > 0 and stale_epochs >= patience:
            print(f"Early stopping at epoch {epoch} after {stale_epochs} stale epochs.")
            break

    history_path.parent.mkdir(parents=True, exist_ok=True)
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "best_epoch": best_epoch,
                "best_val_f1": best_val_f1,
                "epochs_completed": len(history),
                "history": history,
            },
            f,
            indent=2,
        )

    result = {
        "model_path": str(model_path),
        "history_path": str(history_path),
        "best_epoch": best_epoch,
        "best_val_f1": best_val_f1,
        "epochs_completed": len(history),
        "device": device,
        "device_description": describe_device(device),
        "total_train_seconds": round(time.perf_counter() - train_start_time, 2),
    }

    print(json.dumps(result, indent=2))
    return result
