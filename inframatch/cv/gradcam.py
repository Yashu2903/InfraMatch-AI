from pathlib import Path

import cv2
import numpy as np
import torch


class GradCAM:
    def __init__(self, model, target_layer):
        self.model = model
        self.target_layer = target_layer

        self.activations = None
        self.gradients = None

        self.forward_hook = target_layer.register_forward_hook(self.save_activation)
        self.backward_hook = target_layer.register_full_backward_hook(self.save_gradient)

    def save_activation(self, module, input, output):
        self.activations = output.detach()

    def save_gradient(self, module, grad_input, grad_output):
        self.gradients = grad_output[0].detach()

    def __call__(self, input_tensor, class_idx):
        self.model.zero_grad()

        logits = self.model(input_tensor)
        score = logits[:, class_idx].sum()
        score.backward()

        weights = self.gradients.mean(dim=(2, 3), keepdim=True)
        cam = (weights * self.activations).sum(dim=1, keepdim=True)
        cam = torch.relu(cam)

        cam = cam.squeeze().cpu().numpy()

        cam = cam - cam.min()

        if cam.max() > 0:
            cam = cam / cam.max()

        return cam

    def close(self):
        self.forward_hook.remove()
        self.backward_hook.remove()


def make_gradcam(model, input_tensor, class_idx):
    target_layer = model.layer4[-1]
    gradcam = GradCAM(model, target_layer)

    cam = gradcam(input_tensor, class_idx)
    gradcam.close()

    return cam


def overlay_gradcam(original_rgb, cam, output_path: str | Path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    height, width = original_rgb.shape[:2]

    cam_resized = cv2.resize(cam, (width, height))
    heatmap = np.uint8(255 * cam_resized)
    heatmap = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)

    original_bgr = cv2.cvtColor(original_rgb, cv2.COLOR_RGB2BGR)
    overlay = cv2.addWeighted(original_bgr, 0.60, heatmap, 0.40, 0)

    cv2.imwrite(str(output_path), overlay)

    return str(output_path)