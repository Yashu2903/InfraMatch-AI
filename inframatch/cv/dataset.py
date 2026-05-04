from pathlib import Path

import pandas as pd
from PIL import Image
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset
from torchvision import transforms


CLASS_TO_IDX = {
    "no_crack": 0,
    "crack": 1,
}

IDX_TO_CLASS = {
    0: "no_crack",
    1: "crack",
}


def collect_image_paths(data_dir: str | Path) -> pd.DataFrame:
    data_dir = Path(data_dir)

    rows = []

    for class_name, label in CLASS_TO_IDX.items():
        class_dir = data_dir / class_name

        if not class_dir.exists():
            raise FileNotFoundError(f"Missing class folder: {class_dir}")

        for path in class_dir.rglob("*"):
            if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                rows.append(
                    {
                        "path": str(path),
                        "label": label,
                        "class_name": class_name,
                    }
                )

    df = pd.DataFrame(rows)

    if df.empty:
        raise ValueError(f"No images found under {data_dir}")

    return df


def create_splits(
    data_dir: str | Path = "data/sdnet",
    output_dir: str | Path = "data/sdnet_splits",
    seed: int = 42,
) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = collect_image_paths(data_dir)

    train_df, temp_df = train_test_split(
        df,
        test_size=0.30,
        random_state=seed,
        stratify=df["label"],
    )

    val_df, test_df = train_test_split(
        temp_df,
        test_size=0.50,
        random_state=seed,
        stratify=temp_df["label"],
    )

    train_df.to_csv(output_dir / "train.csv", index=False)
    val_df.to_csv(output_dir / "val.csv", index=False)
    test_df.to_csv(output_dir / "test.csv", index=False)

    print("Saved splits:")
    print(f"Train: {len(train_df)}")
    print(f"Val:   {len(val_df)}")
    print(f"Test:  {len(test_df)}")


def train_transforms():
    return transforms.Compose(
        [
            transforms.RandomResizedCrop(224),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(
                brightness=0.15,
                contrast=0.15,
                saturation=0.10,
                hue=0.02,
            ),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ]
    )


def eval_transforms():
    return transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ]
    )


class CrackDataset(Dataset):
    def __init__(self, csv_path: str | Path, transform=None):
        self.df = pd.read_csv(csv_path)
        self.transform = transform

    def __len__(self):
        return len(self.df)

    def __getitem__(self, index):
        row = self.df.iloc[index]

        image = Image.open(row["path"]).convert("RGB")
        label = int(row["label"])

        if self.transform:
            image = self.transform(image)

        return image, label