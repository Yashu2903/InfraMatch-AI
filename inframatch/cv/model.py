from pathlib import Path

import torch
from torch import nn
from torchvision.models import ResNet18_Weights, resnet18


NUM_CLASSES = 2


def build_model(num_classes: int = NUM_CLASSES, pretrained: bool = True):
    weights = ResNet18_Weights.DEFAULT if pretrained else None

    try:
        model = resnet18(weights=weights)
    except Exception:
        model = resnet18(weights=None)

    model.fc = nn.Linear(model.fc.in_features, num_classes)
    return model


def save_checkpoint(
    model,
    output_path: str | Path,
    class_to_idx: dict[str, int] | None = None,
    metadata: dict | None = None,
):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    checkpoint = {
        "state_dict": model.state_dict(),
        "num_classes": model.fc.out_features,
        "class_to_idx": class_to_idx or {"no_crack": 0, "crack": 1},
        "metadata": metadata or {},
    }

    torch.save(checkpoint, output_path)
    return str(output_path)


def load_checkpoint(model_path: str | Path, device: str = "cpu"):
    model_path = Path(model_path)

    if not model_path.exists():
        raise FileNotFoundError(f"Model checkpoint not found: {model_path}")

    checkpoint = torch.load(model_path, map_location=device, weights_only=False)

    if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
        num_classes = int(checkpoint.get("num_classes", NUM_CLASSES))
        state_dict = checkpoint["state_dict"]
    else:
        num_classes = NUM_CLASSES
        state_dict = checkpoint

    model = build_model(num_classes=num_classes, pretrained=False)
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    return model
