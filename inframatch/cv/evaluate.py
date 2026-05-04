import json
from pathlib import Path

import torch
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from torch.utils.data import DataLoader

from inframatch.cv.dataset import CrackDataset, IDX_TO_CLASS, eval_transforms
from inframatch.cv.model import load_checkpoint


def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"


def evaluate_model(
    model_path: str = "models/crack_resnet18.pt",
    test_csv: str = "data/sdnet_splits/test.csv",
    output_path: str = "models/eval_report.json",
    batch_size: int = 32,
):
    device = get_device()

    dataset = CrackDataset(test_csv, transform=eval_transforms())
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0)

    model = load_checkpoint(model_path, device=device)

    all_preds = []
    all_labels = []

    model.eval()

    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)

            logits = model(images)
            preds = torch.argmax(logits, dim=1)

            all_preds.extend(preds.cpu().tolist())
            all_labels.extend(labels.tolist())

    report = {
        "f1": f1_score(all_labels, all_preds, zero_division=0),
        "precision": precision_score(all_labels, all_preds, zero_division=0),
        "recall": recall_score(all_labels, all_preds, zero_division=0),
        "confusion_matrix": confusion_matrix(all_labels, all_preds).tolist(),
        "classification_report": classification_report(
            all_labels,
            all_preds,
            target_names=[IDX_TO_CLASS[0], IDX_TO_CLASS[1]],
            zero_division=0,
            output_dict=True,
        ),
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))
    print(f"\nSaved evaluation report to {output_path}")

    return report