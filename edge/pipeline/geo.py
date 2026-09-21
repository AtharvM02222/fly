"""GPS module with interpolation on dropout."""

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from config import GPSConfig


@dataclass
class GPSReading:
    """GPS reading with interpolation flag."""

    latitude: float
    longitude: float
    timestamp: datetime
    is_interpolated: bool = False


class GPSReader:
    """
    GPS reader with interpolation fallback.

    Supports:
    - Serial GPS (NMEA)
    - Mock GPS for testing
    - Interpolation from last known position when GPS drops
    """

    def __init__(self, config: GPSConfig):
        """
        Initialize GPS reader.

        Args:
            config: GPS configuration
        """
        self.config = config
        self.last_reading: Optional[GPSReading] = None
        self.last_velocity: Optional[tuple[float, float]] = None  # (lat/s, lon/s)

    def read(self) -> Optional[GPSReading]:
        """
        Read current GPS position.

        Returns:
            GPSReading or None if unavailable and interpolation not possible
        """
        # Try to read from GPS
        reading = self._read_from_source()

        if reading is not None:
            # Update last known position and velocity
            if self.last_reading is not None:
                dt = (reading.timestamp - self.last_reading.timestamp).total_seconds()
                if dt > 0:
                    dlat = reading.latitude - self.last_reading.latitude
                    dlon = reading.longitude - self.last_reading.longitude
                    self.last_velocity = (dlat / dt, dlon / dt)

            self.last_reading = reading
            return reading

        # GPS dropout - try interpolation
        if self.config.interpolation.enabled and self.last_reading is not None:
            return self._interpolate()

        return None

    def _read_from_source(self) -> Optional[GPSReading]:
        """
        Read from actual GPS source.

        Returns:
            GPSReading or None if failed
        """
        if self.config.source == "mock":
            # Mock GPS for testing
            return self._mock_gps()

        # TODO: Implement serial GPS reading (NMEA parsing)
        # For now, return None (will trigger interpolation in tests)
        return None

    def _mock_gps(self) -> GPSReading:
        """
        Generate mock GPS reading.

        Returns fixed location (San Francisco) with slight noise.
        """
        # Base location: SF
        base_lat = 37.7749
        base_lon = -122.4194

        # Add small random walk
        noise_lat = np.random.normal(0, 0.0001)
        noise_lon = np.random.normal(0, 0.0001)

        return GPSReading(
            latitude=base_lat + noise_lat,
            longitude=base_lon + noise_lon,
            timestamp=datetime.utcnow(),
            is_interpolated=False,
        )

    def _interpolate(self) -> Optional[GPSReading]:
        """
        Interpolate GPS position from last known location.

        Returns:
            Interpolated GPSReading or None if not possible
        """
        if self.last_reading is None:
            return None

        now = datetime.utcnow()
        age = (now - self.last_reading.timestamp).total_seconds()

        # Check if last reading is too old
        if age > self.config.interpolation.max_age_seconds:
            return None

        # Interpolate using last velocity if available
        if self.last_velocity is not None and self.config.interpolation.use_imu:
            lat_velocity, lon_velocity = self.last_velocity
            interpolated_lat = self.last_reading.latitude + (lat_velocity * age)
            interpolated_lon = self.last_reading.longitude + (lon_velocity * age)
        else:
            # No velocity data - use last known position
            interpolated_lat = self.last_reading.latitude
            interpolated_lon = self.last_reading.longitude

        return GPSReading(
            latitude=interpolated_lat,
            longitude=interpolated_lon,
            timestamp=now,
            is_interpolated=True,
        )
