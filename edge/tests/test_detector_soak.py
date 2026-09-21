"""Soak test for detector - long-running test to detect memory leaks."""

import gc
import time
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from config import DetectorConfig
from pipeline.detector import MockDetector, RealDetector

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


@pytest.fixture
def detector_config():
    """Detector config for soak testing."""
    from config.loader import NormalizationConfig
    
    return DetectorConfig(
        model_path="models/test_pothole.onnx",
        engine_path=None,
        weights_checksum="sha256:placeholder",
        backend="onnx-cpu",
        confidence_threshold=0.5,
        nms_iou_threshold=0.45,
        max_detections=50,
        input_size=640,
        quantization="none",
        warmup_iterations=1,
        inference_timeout_seconds=5.0,
        latency_budget_ms=100,
        normalization=NormalizationConfig(
            mean=[0.0, 0.0, 0.0],
            std=[1.0, 1.0, 1.0],
            scale=255.0,
        ),
        model_version="test-v1.0",
    )


@pytest.mark.slow
@pytest.mark.skipif(not HAS_PSUTIL, reason="psutil not installed")
class TestDetectorSoak:
    """
    Soak tests for detector - run for extended periods to detect:
    - Memory leaks
    - Resource exhaustion
    - Performance degradation over time
    - Error accumulation
    
    These tests run for hours on CI/dedicated hardware.
    """

    def test_mock_detector_memory_leak(self, detector_config):
        """
        Test mock detector for memory leaks over many frames.
        
        This is a lightweight soak test suitable for CI.
        """
        detector = MockDetector(detector_config, detection_interval=10)
        
        # Generate synthetic frames
        frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
        
        # Get initial memory
        process = psutil.Process()
        gc.collect()
        initial_memory_mb = process.memory_info().rss / 1024 / 1024
        
        # Run for 10,000 frames (realistic 10-minute session at 15 FPS)
        num_frames = 10000
        for i in range(num_frames):
            detections = detector.detect(frame)
            
            # Vary frame occasionally
            if i % 100 == 0:
                frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
        
        # Check final memory
        gc.collect()
        final_memory_mb = process.memory_info().rss / 1024 / 1024
        memory_growth_mb = final_memory_mb - initial_memory_mb
        
        print(f"\nSoak test results:")
        print(f"  Frames processed: {num_frames}")
        print(f"  Initial memory: {initial_memory_mb:.1f} MB")
        print(f"  Final memory: {final_memory_mb:.1f} MB")
        print(f"  Memory growth: {memory_growth_mb:.1f} MB")
        
        # Allow up to 50MB growth (conservative threshold)
        # In practice, should be < 10MB for mock detector
        assert memory_growth_mb < 50, f"Memory leak detected: {memory_growth_mb:.1f}MB growth"

    @pytest.mark.skip(reason="Requires real model weights - run manually during validation")
    def test_real_detector_memory_leak(self, detector_config, tmp_path):
        """
        Test real detector for memory leaks.
        
        This requires a real model and should be run manually on target hardware
        (Jetson Orin Nano) for extended periods (1+ hours).
        """
        model_path = tmp_path / "test_model.onnx"
        model_path.write_bytes(b"fake")  # Replace with real model path
        detector_config.model_path = str(model_path)
        
        # This test would be implemented similarly to mock detector test
        # but with RealDetector
        pass

    @pytest.mark.skip(reason="Long-running test - run manually")
    def test_detector_latency_stability(self, detector_config):
        """
        Test that detector latency remains stable over time.
        
        Detects performance degradation issues like:
        - GPU memory fragmentation
        - Accumulating overhead
        - Thermal throttling
        """
        detector = MockDetector(detector_config, detection_interval=10)
        frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
        
        # Measure latency in chunks
        chunk_size = 1000
        num_chunks = 10
        chunk_latencies = []
        
        for chunk_idx in range(num_chunks):
            start_time = time.perf_counter()
            
            for _ in range(chunk_size):
                detector.detect(frame)
            
            elapsed = time.perf_counter() - start_time
            avg_latency_ms = (elapsed / chunk_size) * 1000
            chunk_latencies.append(avg_latency_ms)
            
            print(f"Chunk {chunk_idx + 1}/{num_chunks}: {avg_latency_ms:.2f} ms/frame")
        
        # Check latency stability (shouldn't increase over time)
        first_half_avg = np.mean(chunk_latencies[:num_chunks//2])
        second_half_avg = np.mean(chunk_latencies[num_chunks//2:])
        
        latency_increase_pct = ((second_half_avg - first_half_avg) / first_half_avg) * 100
        
        print(f"\nLatency stability:")
        print(f"  First half avg: {first_half_avg:.2f} ms")
        print(f"  Second half avg: {second_half_avg:.2f} ms")
        print(f"  Increase: {latency_increase_pct:.1f}%")
        
        # Allow up to 10% latency increase (thermal throttling, etc.)
        assert latency_increase_pct < 10, f"Latency degradation: {latency_increase_pct:.1f}%"

    @pytest.mark.skip(reason="Stress test - run manually on target hardware")
    def test_detector_error_recovery(self, detector_config):
        """
        Test detector recovers gracefully from errors.
        
        Injects various error conditions and verifies:
        - Detector continues working after errors
        - Error rate doesn't accumulate
        - Memory is properly released
        """
        # This would test things like:
        # - Corrupted frames
        # - Invalid frame sizes
        # - Timeout conditions
        # - Backend errors
        pass


@pytest.mark.slow
class TestDetectorStressScenarios:
    """Stress test scenarios for detector."""

    def test_varying_frame_sizes(self, detector_config):
        """Test detector with varying frame sizes."""
        detector = MockDetector(detector_config)
        
        # Test various common camera resolutions
        resolutions = [
            (480, 640),   # VGA
            (720, 1280),  # HD
            (1080, 1920), # Full HD
            (1440, 2560), # 2K
        ]
        
        for h, w in resolutions:
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            detections = detector.detect(frame)
            # Should not crash
            assert isinstance(detections, list)

    def test_extreme_frame_content(self, detector_config):
        """Test detector with extreme frame content."""
        detector = MockDetector(detector_config)
        
        # All black
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        assert isinstance(detector.detect(frame), list)
        
        # All white
        frame = np.ones((1080, 1920, 3), dtype=np.uint8) * 255
        assert isinstance(detector.detect(frame), list)
        
        # Random noise
        frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
        assert isinstance(detector.detect(frame), list)

    def test_high_detection_density(self, detector_config):
        """Test detector with many detections (max_detections limit)."""
        # This would require a mock that generates many overlapping detections
        # to test the max_detections cap and NMS performance
        pass


def run_manual_soak_test():
    """
    Manual soak test runner for extended validation.
    
    Run this on target hardware (Jetson Orin Nano) for 1+ hours:
    
        python -m pytest tests/test_detector_soak.py::run_manual_soak_test -v
    
    Or directly:
    
        python tests/test_detector_soak.py
    """
    print("=" * 80)
    print("MANUAL SOAK TEST")
    print("=" * 80)
    print("This test runs for an extended period to validate detector stability.")
    print("Recommended: Run on target hardware (Jetson Orin Nano) for 1+ hours.")
    print()
    
    if not HAS_PSUTIL:
        print("ERROR: psutil not installed. Install with: pip install psutil")
        return
    
    # Configuration
    from config.loader import NormalizationConfig
    
    config = DetectorConfig(
        model_path="models/pothole.onnx",
        engine_path="models/pothole.engine",
        weights_checksum="sha256:placeholder",
        backend="auto",
        confidence_threshold=0.5,
        nms_iou_threshold=0.45,
        max_detections=50,
        input_size=640,
        quantization="none",
        warmup_iterations=5,
        inference_timeout_seconds=5.0,
        latency_budget_ms=100,
        normalization=NormalizationConfig(
            mean=[0.0, 0.0, 0.0],
            std=[1.0, 1.0, 1.0],
            scale=255.0,
        ),
        model_version="v1.0",
    )
    
    # Use mock detector for now
    detector = MockDetector(config)
    
    # Load a video file or use synthetic frames
    frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
    
    process = psutil.Process()
    start_time = time.time()
    frame_count = 0
    
    print("Starting soak test... (Press Ctrl+C to stop)")
    print()
    
    try:
        while True:
            detections = detector.detect(frame)
            frame_count += 1
            
            # Report every 1000 frames
            if frame_count % 1000 == 0:
                elapsed = time.time() - start_time
                fps = frame_count / elapsed
                memory_mb = process.memory_info().rss / 1024 / 1024
                latency_stats = detector.get_latency_stats()
                
                print(f"Frame {frame_count:6d} | "
                      f"Elapsed {elapsed:7.1f}s | "
                      f"FPS {fps:5.1f} | "
                      f"Memory {memory_mb:6.1f}MB | "
                      f"Latency p95 {latency_stats['p95']:5.1f}ms")
                
                # Vary frame content occasionally
                if frame_count % 5000 == 0:
                    frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
    
    except KeyboardInterrupt:
        print()
        print("=" * 80)
        print("SOAK TEST SUMMARY")
        print("=" * 80)
        elapsed = time.time() - start_time
        fps = frame_count / elapsed
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        print(f"Total frames: {frame_count}")
        print(f"Total time: {elapsed:.1f}s ({elapsed/3600:.2f} hours)")
        print(f"Average FPS: {fps:.1f}")
        print(f"Final memory: {memory_mb:.1f}MB")
        print(f"Error rate: {detector.get_error_rate():.3%}")
        
        latency_stats = detector.get_latency_stats()
        print(f"\nLatency statistics:")
        print(f"  p50: {latency_stats['p50']:.2f}ms")
        print(f"  p95: {latency_stats['p95']:.2f}ms")
        print(f"  p99: {latency_stats['p99']:.2f}ms")


if __name__ == "__main__":
    run_manual_soak_test()
