# Phase 5 Explanation

This document explains the Phase 5 computer-vision training pipeline in simple
language.

Phase 5 extends InfraMatch beyond supplier-opportunity matching.

The main goal of Phase 5 is:

- add an image classifier for crack detection
- train that classifier on SDNET-style crack vs no-crack imagery
- evaluate the trained model with standard metrics
- support single-image inference
- produce Grad-CAM visual explanations for positive detections

In short:

- Phases 1 to 4 built the procurement data and matching system
- Phase 5 adds a vision model that can inspect infrastructure imagery


## 1. What Phase 5 Adds

Phase 5 introduces a new `inframatch/cv/` package and supporting scripts.

The new code covers:

- dataset loading
- train/validation/test split generation
- image transforms
- ResNet18 model construction
- training with early stopping
- checkpoint saving
- evaluation on a held-out test set
- single-image prediction
- Grad-CAM heatmap generation
- simple crack-severity estimation


## 2. Files Used in Phase 5

### `inframatch/cv/dataset.py`

This file is responsible for:

- defining the two classes:
  - `no_crack -> 0`
  - `crack -> 1`
- collecting image paths from the dataset folder
- creating train, validation, and test CSV split files
- defining training transforms
- defining evaluation transforms
- loading samples through `CrackDataset`

### `inframatch/cv/model.py`

This file is responsible for:

- building a ResNet18 classifier
- optionally loading ImageNet pretrained weights
- replacing the final classification head for two classes
- saving checkpoints
- loading checkpoints for inference and evaluation

### `inframatch/cv/train.py`

This is the main training module.

It handles:

- device selection
- random seed setup
- split creation if CSVs do not already exist
- class weighting for imbalance
- dataloader creation
- training loop execution
- validation at the end of each epoch
- best-model checkpointing
- early stopping
- history export to JSON

### `inframatch/cv/evaluate.py`

This module runs held-out evaluation and writes:

- F1 score
- precision
- recall
- confusion matrix
- full classification report

### `inframatch/cv/inference.py`

This module runs single-image prediction and returns:

- predicted class
- confidence
- class probabilities
- crack ratio estimate
- severity bin
- Grad-CAM output path when a crack is detected

### `inframatch/cv/gradcam.py`

This file implements Grad-CAM support by:

- attaching hooks to the last ResNet block
- capturing activations and gradients
- generating a normalized heatmap
- overlaying that heatmap on the original image

### `scripts/train_crack_model.py`

CLI entry point for model training.

### `scripts/evaluate_crack_model.py`

CLI entry point for held-out evaluation.

### `scripts/predict_crack.py`

CLI entry point for single-image prediction.


## 3. Dataset Structure

The Phase 5 training code expects a directory layout like this:

```text
data/sdnet/
  crack/
  no_crack/
```

The loader scans those folders recursively for:

- `.jpg`
- `.jpeg`
- `.png`

The labels are binary:

- `0` for `no_crack`
- `1` for `crack`


## 4. Split Strategy

If split CSV files are missing, `create_splits(...)` generates them
automatically.

The split policy is:

- `70%` training
- `15%` validation
- `15%` test

The split is stratified by label, so the crack / no-crack ratio stays similar
across all three splits.

With the current local Phase 5 dataset, the generated splits are:

- train: `39,264` images
- validation: `8,414` images
- test: `8,414` images

Class counts are currently:

- train:
  - `33,325` no-crack
  - `5,939` crack
- validation:
  - `7,141` no-crack
  - `1,273` crack
- test:
  - `7,142` no-crack
  - `1,272` crack

This shows a clear class imbalance, which is why weighted loss is used during
training.


## 5. Image Preprocessing and Augmentation

### Training transforms

Training uses:

- `RandomResizedCrop(224)`
- `RandomHorizontalFlip()`
- `ColorJitter(...)`
- ImageNet normalization

Why this matters:

- random crops help generalization
- horizontal flips reduce directional bias
- mild color jitter improves robustness to lighting and surface variation
- normalization matches the ResNet18 backbone expectation

### Evaluation transforms

Validation and test images use:

- `Resize((224, 224))`
- ImageNet normalization

This keeps evaluation deterministic.


## 6. Model Architecture

Phase 5 uses `torchvision.models.resnet18`.

Important details:

- default behavior is to use pretrained ImageNet weights
- if pretrained weights fail to load, the code falls back to uninitialized
  weights
- the final fully connected layer is replaced for binary classification

Why ResNet18 is a reasonable Phase 5 choice:

- small enough to train efficiently
- strong baseline for image classification
- compatible with transfer learning
- simple to explain and deploy


## 7. Training Configuration

The training CLI currently defaults to:

- batch size: `32`
- epochs: `5`
- learning rate: `1e-4`
- weight decay: `1e-4`
- patience: `3`
- seed: `42`
- pretrained backbone: enabled by default

These defaults come from `scripts/train_crack_model.py`.

The optimizer is:

- `Adam`

The loss function is:

- `CrossEntropyLoss`

The loss is class-weighted based on training-set label frequencies.

This is important because the dataset has many more no-crack images than crack
images.


## 8. Device Handling

The training code checks for CUDA first.

Behavior:

- if CUDA is available, it trains on GPU
- otherwise it trains on CPU
- `--require-cuda` forces training to fail if no GPU is available

When CUDA is used, the code also enables:

- `torch.backends.cudnn.benchmark = True`

That improves runtime performance for fixed-size image batches.


## 9. Training Loop Behavior

For each epoch, the pipeline:

1. runs forward and backward passes on the training set
2. computes training loss and training accuracy
3. evaluates on the validation set
4. computes validation loss, validation accuracy, and validation F1
5. saves the best checkpoint whenever validation F1 improves
6. stops early if validation F1 does not improve for the configured patience

Validation F1 is used as the checkpoint-selection target because:

- the dataset is imbalanced
- crack detection quality matters more than raw accuracy alone


## 10. Saved Artifacts

Training writes two main artifacts:

- `models/crack_resnet18.pt`
- `models/crack_resnet18_history.json`

The checkpoint stores:

- model state dict
- number of classes
- `class_to_idx`
- metadata such as:
  - `best_epoch`
  - `best_val_f1`
  - `seed`

The history JSON stores:

- best epoch
- best validation F1
- number of completed epochs
- per-epoch metrics
- per-epoch runtime details


## 11. Current Recorded Training Results

The current local training history shows:

- best epoch: `5`
- best validation F1: `0.7517`
- epochs completed: `5`

Per-epoch validation F1 values were:

- epoch 1: `0.6537`
- epoch 2: `0.7253`
- epoch 3: `0.6637`
- epoch 4: `0.7123`
- epoch 5: `0.7517`

This indicates:

- the model improved materially after the first epoch
- validation performance was somewhat noisy
- the best checkpoint came at the last completed epoch in the recorded run


## 12. Evaluation Pipeline

Held-out evaluation is implemented in `inframatch/cv/evaluate.py`.

It:

- loads the saved checkpoint
- runs inference on the test split
- computes classification metrics
- writes them to `models/eval_report.json`

The current local evaluation report shows:

- F1: `0.7600`
- precision: `0.7216`
- recall: `0.8027`
- overall accuracy: `0.9233`

Current confusion matrix:

```text
[[6748, 394],
 [ 251, 1021]]
```

Interpretation:

- the model performs strongly on the majority no-crack class
- recall on the crack class is higher than precision
- that means the model catches many crack cases, but still produces some false
  positives


## 13. Class-Level Evaluation Details

The recorded class report shows:

### `no_crack`

- precision: `0.9641`
- recall: `0.9448`
- F1: `0.9544`

### `crack`

- precision: `0.7216`
- recall: `0.8027`
- F1: `0.7600`

This is a sensible Phase 5 profile for safety-oriented screening because:

- missing true cracks is usually more costly than flagging some extra images
- recall on the crack class is therefore especially important


## 14. Inference Behavior

Single-image inference is implemented in `predict(...)`.

The prediction flow is:

1. load the checkpoint
2. preprocess the image with evaluation transforms
3. run the model
4. convert logits to probabilities with softmax
5. compare crack probability against the threshold
6. return a structured JSON result

The default threshold is:

- `0.5`

If the result is `no_crack`, the output returns:

- prediction
- confidence
- `prob_crack`
- `prob_no_crack`
- no severity
- no Grad-CAM file

If the result is `crack`, the output additionally returns:

- Grad-CAM visualization path
- estimated crack ratio
- severity bucket


## 15. Grad-CAM and Severity Estimation

Grad-CAM is only generated for positive crack predictions.

The code:

- targets the last residual block: `model.layer4[-1]`
- computes a class-specific heatmap
- rescales it to image size
- overlays it on the original image
- saves the overlay under `outputs/gradcam/`

After that, the inference path estimates a simple crack ratio by:

- resizing the CAM to original image size
- thresholding the CAM at `0.5`
- detecting image edges with Canny
- measuring edge density inside the activated CAM region

Severity bins are:

- `low` if crack ratio `< 0.005`
- `medium` if crack ratio `< 0.02`
- `high` otherwise

This severity logic is heuristic.

It is useful for demos and explainability, but it is not a calibrated civil
engineering damage metric.


## 16. Command-Line Usage

### Train

```bash
python scripts/train_crack_model.py
```

Optional flags include:

- `--data-dir`
- `--splits-dir`
- `--model-path`
- `--history-path`
- `--batch-size`
- `--epochs`
- `--learning-rate`
- `--weight-decay`
- `--patience`
- `--seed`
- `--no-pretrained`
- `--require-cuda`

### Evaluate

```bash
python scripts/evaluate_crack_model.py
```

Optional flags include:

- `--model-path`
- `--test-csv`
- `--output-path`
- `--batch-size`

### Predict

```bash
python scripts/predict_crack.py path/to/image.jpg
```

Optional flags include:

- `--model-path`
- `--gradcam-dir`
- `--threshold`


## 17. Dependencies Added for Phase 5

The repo requirements now include the main CV stack:

- `torch`
- `torchvision`
- `scikit-learn`
- `pillow`
- `opencv-python`
- `matplotlib`
- `numpy`

These support:

- model training
- evaluation metrics
- image loading
- Grad-CAM generation
- crack-ratio estimation


## 18. Why Phase 5 Matters

Until Phase 4, InfraMatch focused on matching suppliers to opportunities.

Phase 5 adds a second capability:

- visual inspection support for infrastructure imagery

That matters because many infrastructure workflows combine:

- procurement decisions
- inspection evidence
- compliance and maintenance follow-up

Even as a baseline model, this phase shows how InfraMatch can extend from data
matching into image-based decision support.


## 19. Known Limitations

Phase 5 is useful, but it is still an early-stage vision pipeline.

Important limitations:

- the classifier is binary only
- it does not localize cracks with pixel-accurate segmentation
- Grad-CAM is explainable, but not a precise defect mask
- severity is heuristic, not domain-calibrated
- performance is measured on the current held-out split only
- no probability calibration or threshold tuning has been added yet
- no dedicated API serving layer is included in the current Phase 5 code


## 20. Simple Summary

In simple terms, Phase 5 did five important things:

1. It added a crack vs no-crack image classification pipeline.
2. It trained a ResNet18 model on SDNET-style image folders.
3. It evaluated the model with F1, precision, recall, and confusion matrix.
4. It added single-image inference with confidence scores.
5. It added Grad-CAM overlays and a simple severity estimate for positive
   detections.

That is why this phase matters.

It turns InfraMatch from a pure matching system into a project that also has a
working computer-vision inspection component.
