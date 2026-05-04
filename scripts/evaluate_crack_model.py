import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from inframatch.cv.evaluate import evaluate_model


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--model-path", default="models/crack_resnet18.pt")
    parser.add_argument("--test-csv", default="data/sdnet_splits/test.csv")
    parser.add_argument("--output-path", default="models/eval_report.json")
    parser.add_argument("--batch-size", type=int, default=32)

    args = parser.parse_args()

    evaluate_model(
        model_path=args.model_path,
        test_csv=args.test_csv,
        output_path=args.output_path,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
