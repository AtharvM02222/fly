import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import numpy as np
from config import GPSConfig
@dataclass
class GPSReading:
    latitude: float
    longitude: float
    timestamp: datetime
    is_interpolated: bool = False
class GPSReader:
    def __init__(self, config: GPSConfig):
        self.config = config
        self.last_reading: Optional[GPSReading] = None
        self.last_velocity: Optional[tuple[float, float]] = None
    def read(self) -> Optional[GPSReading]:
        reading = self._read_from_source()
        if reading is not None:
            if self.last_reading is not None:
                dt = (reading.timestamp - self.last_reading.timestamp).total_seconds()
                if dt > 0:
                    dlat = reading.latitude - self.last_reading.latitude
                    dlon = reading.longitude - self.last_reading.longitude
                    self.last_velocity = (dlat / dt, dlon / dt)
            self.last_reading = reading
            return reading
        if self.config.interpolation.enabled and self.last_reading is not None:
            return self._interpolate()
        return None
    def _read_from_source(self) -> Optional[GPSReading]:
        if self.config.source == "mock":
            return self._mock_gps()
        return None
    def _mock_gps(self) -> GPSReading:
        base_lat = 37.7749
        base_lon = -122.4194
        noise_lat = np.random.normal(0, 0.0001)
        noise_lon = np.random.normal(0, 0.0001)
        return GPSReading(
            latitude=base_lat + noise_lat,
            longitude=base_lon + noise_lon,
            timestamp=datetime.utcnow(),
            is_interpolated=False,
        )
    def _interpolate(self) -> Optional[GPSReading]:
        if self.last_reading is None:
            return None
        now = datetime.utcnow()
        age = (now - self.last_reading.timestamp).total_seconds()
        if age > self.config.interpolation.max_age_seconds:
            return None
        if self.last_velocity is not None and self.config.interpolation.use_imu:
            lat_velocity, lon_velocity = self.last_velocity
            interpolated_lat = self.last_reading.latitude + (lat_velocity * age)
            interpolated_lon = self.last_reading.longitude + (lon_velocity * age)
        else:
            interpolated_lat = self.last_reading.latitude
            interpolated_lon = self.last_reading.longitude
        return GPSReading(
            latitude=interpolated_lat,
            longitude=interpolated_lon,
            timestamp=now,
            is_interpolated=True,
        )
