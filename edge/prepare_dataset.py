import argparse
import shutil
from pathlib import Path
import yaml
def create_yolo_dataset(
    images_dir: str,
    labels_dir: str,
    output_dir: str,
    train_split: float = 0.8,
    val_split: float = 0.1,
):
    images_path = Path(images_dir)
    labels_path = Path(labels_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "images" / "train").mkdir(parents=True, exist_ok=True)
    (output_path / "images" / "val").mkdir(parents=True, exist_ok=True)
    (output_path / "images" / "test").mkdir(parents=True, exist_ok=True)
    (output_path / "labels" / "train").mkdir(parents=True, exist_ok=True)
    (output_path / "labels" / "val").mkdir(parents=True, exist_ok=True)
    (output_path / "labels" / "test").mkdir(parents=True, exist_ok=True)
    image_files = sorted(list(images_path.glob("*.jpg")) + list(images_path.glob("*.png")))
    total = len(image_files)
    train_count = int(total * train_split)
    val_count = int(total * val_split)
    train_images = image_files[:train_count]
    val_images = image_files[train_count:train_count + val_count]
    test_images = image_files[train_count + val_count:]
    def copy_files(image_list, split):
        for img_file in image_list:
            label_file = labels_path / f"{img_file.stem}.txt"
            if not label_file.exists():
                print(f"Warning: No label for {img_file.name}")
                continue
            shutil.copy(img_file, output_path / "images" / split / img_file.name)
            shutil.copy(label_file, output_path / "labels" / split / label_file.name)
    print(f"Copying {len(train_images)} training images...")
    copy_files(train_images, "train")
    print(f"Copying {len(val_images)} validation images...")
    copy_files(val_images, "val")
    print(f"Copying {len(test_images)} test images...")
    copy_files(test_images, "test")
    data_yaml = {
        "path": str(output_path.absolute()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "nc": 1,
        "names": ["pothole"]
    }
    with open(output_path / "data.yaml", "w") as f:
        yaml.dump(data_yaml, f, default_flow_style=False)
    print(f"\nDataset created: {output_path}")
    print(f"  Train: {len(train_images)} images")
    print(f"  Val: {len(val_images)} images")
    print(f"  Test: {len(test_images)} images")
    print(f"  Config: {output_path}/data.yaml")
    return output_path / "data.yaml"
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare YOLO dataset from images and labels")
    parser.add_argument("--images", type=str, required=True, help="Directory with images")
    parser.add_argument("--labels", type=str, required=True, help="Directory with YOLO labels")
    parser.add_argument("--output", type=str, required=True, help="Output directory")
    parser.add_argument("--train-split", type=float, default=0.8, help="Training split ratio")
    parser.add_argument("--val-split", type=float, default=0.1, help="Validation split ratio")
    args = parser.parse_args()
    create_yolo_dataset(
        images_dir=args.images,
        labels_dir=args.labels,
        output_dir=args.output,
        train_split=args.train_split,
        val_split=args.val_split,
    )
