# Multi-stage Dockerfile for Drone-CDS Edge Pipeline
# Supports both x86_64 (dev/Raspberry Pi) and arm64 (Jetson)

FROM python:3.11-slim as base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 edgeuser && \
    chown -R edgeuser:edgeuser /app

USER edgeuser

# Default command (can be overridden)
CMD ["python", "main.py"]
