"""
Drone-CDS Edge Pipeline Entry Point

This is the main orchestrator for the edge detection pipeline.
Coordinates capture, detection, tracking, geo, buffer, and uplink modules.
"""

import argparse
import logging
import sys
from pathlib import Path

from config import load_config

# TODO: Import pipeline modules as they're implemented
# from pipeline import capture, detector, tracker, severity, geo, buffer, uplink


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Setup basic logging for edge pipeline."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    return logging.getLogger(__name__)


def main() -> int:
    """Main entry point for edge pipeline."""
    parser = argparse.ArgumentParser(description="Drone-CDS Edge Detection Pipeline")
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file (default: config/default.yaml)"
    )
    parser.add_argument(
        "--detector",
        type=str,
        choices=["real", "mock"],
        default="real",
        help="Detector type: real (ONNX/TensorRT) or mock (for testing)"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )

    args = parser.parse_args()

    logger = setup_logging(args.log_level)
    logger.info("Starting Drone-CDS Edge Pipeline")

    try:
        # Load configuration
        config = load_config(args.config)
        logger.info(f"Configuration loaded successfully")
        logger.info(f"Device ID: {config.device.id}")
        logger.info(f"Backend URL: {config.backend.url}")
        logger.info(f"Detector backend: {config.detector.backend}")

        # TODO: Initialize pipeline modules
        # TODO: Start capture thread
        # TODO: Start detection loop
        # TODO: Start uplink thread

        logger.info("Edge pipeline initialization complete")
        logger.warning("Pipeline modules not yet implemented - exiting")

        return 0

    except Exception as e:
        logger.error(f"Failed to start edge pipeline: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
