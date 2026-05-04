import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from inframatch.cv.inference import predict


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("image_path")
    parser.add_argument("--model-path", default="models/crack_resnet18.pt")
    parser.add_argument("--gradcam-dir", default="outputs/gradcam")
    parser.add_argument("--threshold", type=float, default=0.5)

    args = parser.parse_args()

    result = predict(
        image_path=args.image_path,
        model_path=args.model_path,
        gradcam_dir=args.gradcam_dir,
        threshold=args.threshold,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
