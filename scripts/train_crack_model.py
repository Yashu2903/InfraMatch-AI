import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from inframatch.cv.train import train_model


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--data-dir", default="data/sdnet")
    parser.add_argument("--splits-dir", default="data/sdnet_splits")
    parser.add_argument("--model-path", default="models/crack_resnet18.pt")
    parser.add_argument("--history-path", default=None)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-pretrained", action="store_true")
    parser.add_argument("--require-cuda", action="store_true")

    args = parser.parse_args()

    train_model(
        data_dir=args.data_dir,
        splits_dir=args.splits_dir,
        model_path=args.model_path,
        history_path=args.history_path,
        batch_size=args.batch_size,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        patience=args.patience,
        seed=args.seed,
        pretrained=not args.no_pretrained,
        require_cuda=args.require_cuda,
    )


if __name__ == "__main__":
    main()
