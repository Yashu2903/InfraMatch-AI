import uuid
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

from inframatch.cv.dataset import IDX_TO_CLASS, eval_transforms
from inframatch.cv.gradcam import make_gradcam, overlay_gradcam
from inframatch.cv.model import load_checkpoint


def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_image(image_path: str | Path):
    image_path = Path(image_path)

    image = Image.open(image_path).convert("RGB")
    original_rgb = np.array(image)

    transform = eval_transforms()
    tensor = transform(image).unsqueeze(0)

    return original_rgb, tensor


def bin_severity(crack_ratio: float) -> str:
    if crack_ratio < 0.005:
        return "low"
    if crack_ratio < 0.02:
        return "medium"
    return "high"


def estimate_crack_ratio(original_rgb, cam):
    height, width = original_rgb.shape[:2]

    cam_resized = cv2.resize(cam, (width, height))
    cam_mask = cam_resized > 0.5

    mask_area = cam_mask.sum()

    if mask_area == 0:
        return 0.0

    gray = cv2.cvtColor(original_rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    edges_in_mask = edges * cam_mask

    crack_ratio = edges_in_mask.sum() / mask_area / 255.0

    return float(crack_ratio)


def predict(
    image_path: str | Path,
    model_path: str | Path = "models/crack_resnet18.pt",
    gradcam_dir: str | Path = "outputs/gradcam",
    threshold: float = 0.5,
) -> dict:
    device = get_device()

    model = load_checkpoint(str(model_path), device=device)

    original_rgb, tensor = load_image(image_path)
    tensor = tensor.to(device)

    model.eval()

    with torch.no_grad():
        logits = model(tensor)
        probs = torch.softmax(logits, dim=1)[0]

    prob_no_crack = float(probs[0].detach().cpu())
    prob_crack = float(probs[1].detach().cpu())

    prediction_idx = 1 if prob_crack >= threshold else 0
    prediction = IDX_TO_CLASS[prediction_idx]
    confidence = max(prob_no_crack, prob_crack)

    if prediction == "no_crack":
        return {
            "prediction": "no_crack",
            "confidence": round(confidence, 4),
            "severity": "n/a",
            "crack_ratio": None,
            "gradcam_path": None,
            "prob_crack": round(prob_crack, 4),
            "prob_no_crack": round(prob_no_crack, 4),
        }

    cam = make_gradcam(model, tensor, class_idx=1)

    crack_ratio = estimate_crack_ratio(original_rgb, cam)
    severity = bin_severity(crack_ratio)

    image_stem = Path(image_path).stem
    output_name = f"{image_stem}_{uuid.uuid4().hex[:8]}_gradcam.jpg"
    gradcam_path = Path(gradcam_dir) / output_name

    overlay_path = overlay_gradcam(original_rgb, cam, gradcam_path)

    return {
        "prediction": "crack",
        "confidence": round(confidence, 4),
        "severity": severity,
        "crack_ratio": round(crack_ratio, 6),
        "gradcam_path": overlay_path,
        "prob_crack": round(prob_crack, 4),
        "prob_no_crack": round(prob_no_crack, 4),
    }