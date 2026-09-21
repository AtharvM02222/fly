import argparse
from pathlib import Path
from ultralytics import YOLO
def train_yolov8n(
    data_yaml: str,
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = 16,
    name: str = "pothole_detector",
    device: str = "0",
):
    model = YOLO("yolov8n.pt")
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        name=name,
        device=device,
        patience=20,
        save=True,
        save_period=10,
        project="runs/detect",
        exist_ok=True,
        pretrained=True,
        optimizer="Adam",
        lr0=0.01,
        lrf=0.01,
        momentum=0.937,
        weight_decay=0.0005,
        warmup_epochs=3.0,
        warmup_momentum=0.8,
        warmup_bias_lr=0.1,
        box=7.5,
        cls=0.5,
        dfl=1.5,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=0.0,
        translate=0.1,
        scale=0.5,
        shear=0.0,
        perspective=0.0,
        flipud=0.0,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.0,
        copy_paste=0.0,
    )
    print(f"\nTraining complete. Best model: {results.save_dir}/weights/best.pt")
    return results
def export_to_onnx(model_path: str, output_dir: str = "./models"):
    model = YOLO(model_path)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    onnx_path = model.export(
        format="onnx",
        imgsz=640,
        simplify=True,
        opset=12,
        dynamic=False,
    )
    print(f"\nONNX export complete: {onnx_path}")
    return onnx_path
def export_to_tensorrt(model_path: str, output_dir: str = "./models"):
    model = YOLO(model_path)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    trt_path = model.export(
        format="engine",
        imgsz=640,
        half=True,
        device=0,
        workspace=4,
    )
    print(f"\nTensorRT export complete: {trt_path}")
    return trt_path
def validate_model(model_path: str, data_yaml: str):
    model = YOLO(model_path)
    metrics = model.val(data=data_yaml, imgsz=640, batch=16, conf=0.25, iou=0.6)
    print(f"\nValidation Results:")
    print(f"  mAP50: {metrics.box.map50:.4f}")
    print(f"  mAP50-95: {metrics.box.map:.4f}")
    print(f"  Precision: {metrics.box.p[0]:.4f}")
    print(f"  Recall: {metrics.box.r[0]:.4f}")
    return metrics
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train YOLOv8n pothole detector")
    parser.add_argument("--data", type=str, required=True, help="Path to data.yaml")
    parser.add_argument("--epochs", type=int, default=100, help="Number of epochs")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size")
    parser.add_argument("--device", type=str, default="0", help="Device (0, 1, cpu)")
    parser.add_argument("--name", type=str, default="pothole_detector", help="Run name")
    parser.add_argument("--export-onnx", action="store_true", help="Export to ONNX after training")
    parser.add_argument("--export-trt", action="store_true", help="Export to TensorRT after training")
    parser.add_argument("--validate", action="store_true", help="Validate after training")
    args = parser.parse_args()
    print("="*60)
    print("YOLOv8n Pothole Detector Training")
    print("="*60)
    results = train_yolov8n(
        data_yaml=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        name=args.name,
        device=args.device,
    )
    best_model = f"{results.save_dir}/weights/best.pt"
    if args.validate:
        print("\n" + "="*60)
        print("Validating model...")
        print("="*60)
        validate_model(best_model, args.data)
    if args.export_onnx:
        print("\n" + "="*60)
        print("Exporting to ONNX...")
        print("="*60)
        export_to_onnx(best_model)
    if args.export_trt:
        print("\n" + "="*60)
        print("Exporting to TensorRT...")
        print("="*60)
        export_to_tensorrt(best_model)
    print("\n" + "="*60)
    print("All tasks complete!")
    print("="*60)
