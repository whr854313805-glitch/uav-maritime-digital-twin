"""
Maritime Vessel Agent Models

Defines vessel types and behaviors for the maritime traffic simulator.
Supports: Ferries, cargo ships, yachts with different movement patterns.
"""

import numpy as np
from dataclasses import dataclass
from typing import Tuple, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Geographic position (lat, lon, altitude)"""
    lat: float
    lon: float
    alt: float = 0.0

    def distance_to(self, other: 'Position') -> float:
        """Approximate distance in meters (simplified)"""
        lat_diff = (other.lat - self.lat) * 111000  # meters per degree
        lon_diff = (other.lon - self.lon) * 111000 * np.cos(np.radians(self.lat))
        return np.sqrt(lat_diff**2 + lon_diff**2)


class VesselAgent:
    """
    Base vessel agent with position, velocity, and fairway constraints
    """

    def __init__(self, vessel_id: str, vessel_type: str,
                 start_pos: Position, end_pos: Position,
                 max_speed: float = 10.0):
        """
        Initialize vessel agent

        Args:
            vessel_id: Unique identifier
            vessel_type: 'ferry', 'cargo', 'yacht'
            start_pos: Starting position
            end_pos: Destination
            max_speed: Maximum speed in m/s
        """
        self.vessel_id = vessel_id
        self.vessel_type = vessel_type
        self.position = start_pos
        self.destination = end_pos
        self.max_speed = max_speed
        self.current_speed = 0.0
        self.heading = 0.0  # degrees from north
        self.velocity = np.array([0.0, 0.0, 0.0])  # [lat_vel, lon_vel, alt_vel]

        # Agent state
        self.active = True
        self.in_fairway = False
        self.collision_risk = False
        self.created_at = datetime.now()

    def update_position(self, dt: float, wind_data: dict = None) -> None:
        """
        Update vessel position based on time step

        Args:
            dt: Time step in seconds
            wind_data: Dictionary with 'speed' and 'direction' (m/s, degrees)
        """
        if not self.active:
            return

        # Calculate direction to destination
        distance = self.position.distance_to(self.destination)

        if distance < 100:  # Within 100m of destination
            self.active = False
            logger.debug(f"Vessel {self.vessel_id} reached destination")
            return

        # Calculate bearing to destination
        lat_diff = self.destination.lat - self.position.lat
        lon_diff = self.destination.lon - self.position.lon
        bearing = np.arctan2(lon_diff, lat_diff)

        # Apply wind perturbation if provided
        if wind_data:
            wind_speed = wind_data.get('speed', 0)
            wind_dir = np.radians(wind_data.get('direction', 0))

            # Wind affects heading
            wind_effect = 0.1 * wind_speed * np.sin(wind_dir - bearing)
            bearing += wind_effect * 0.01

        # Update heading
        self.heading = np.degrees(bearing)

        # Set velocity based on vessel type and current speed
        current_speed = self._get_current_speed()
        lat_vel = current_speed * np.cos(bearing)
        lon_vel = current_speed * np.sin(bearing)

        # Update position
        self.position.lat += lat_vel * dt / 111000
        self.position.lon += lon_vel * dt / (111000 * np.cos(np.radians(self.position.lat)))
        self.position.alt = 0  # Marine vessels stay at sea level

        self.velocity = np.array([lat_vel, lon_vel, 0.0])
        self.current_speed = current_speed

    def _get_current_speed(self) -> float:
        """
        Get current speed based on vessel type and distance to destination

        Returns:
            Speed in m/s
        """
        distance = self.position.distance_to(self.destination)

        if self.vessel_type == 'ferry':
            # Ferries are fast and consistent
            return min(self.max_speed, 12.0)

        elif self.vessel_type == 'cargo':
            # Cargo ships are slower
            return min(self.max_speed, 7.0)

        elif self.vessel_type == 'yacht':
            # Yachts vary speed
            return min(self.max_speed, 8.0 + 2.0 * np.sin(datetime.now().timestamp() / 100))

        return self.max_speed

    def check_fairway_boundary(self, fairway_bounds: dict) -> bool:
        """
        Check if vessel is within fairway bounds

        Args:
            fairway_bounds: Dict with 'lat_min', 'lat_max', 'lon_min', 'lon_max'

        Returns:
            True if within bounds, False otherwise
        """
        in_bounds = (
            fairway_bounds['lat_min'] <= self.position.lat <= fairway_bounds['lat_max'] and
            fairway_bounds['lon_min'] <= self.position.lon <= fairway_bounds['lon_max']
        )

        self.in_fairway = in_bounds
        return in_bounds

    def distance_to_vessel(self, other: 'VesselAgent') -> float:
        """Calculate distance to another vessel"""
        return self.position.distance_to(other.position)

    def set_collision_risk(self, risk: bool) -> None:
        """Mark if vessel has collision risk"""
        self.collision_risk = risk

    def get_state(self) -> dict:
        """Return current vessel state as dictionary"""
        return {
            'vessel_id': self.vessel_id,
            'vessel_type': self.vessel_type,
            'latitude': self.position.lat,
            'longitude': self.position.lon,
            'altitude': self.position.alt,
            'speed': self.current_speed,
            'heading': self.heading,
            'active': self.active,
            'in_fairway': self.in_fairway,
            'collision_risk': self.collision_risk
        }


class FerryAgent(VesselAgent):
    """Ferry vessel with scheduled route"""

    def __init__(self, vessel_id: str, start_pos: Position,
                 end_pos: Position, schedule: List[Tuple] = None):
        super().__init__(vessel_id, 'ferry', start_pos, end_pos, max_speed=12.0)
        self.schedule = schedule or []  # List of (time, position) tuples
        self.schedule_index = 0


class CargoAgent(VesselAgent):
    """Cargo ship with slower movement"""

    def __init__(self, vessel_id: str, start_pos: Position, end_pos: Position):
        super().__init__(vessel_id, 'cargo', start_pos, end_pos, max_speed=7.0)
        self.cargo_weight = 10000  # tons
        self.draft = 5.0  # meters


class YachtAgent(VesselAgent):
    """Yacht with variable speed"""

    def __init__(self, vessel_id: str, start_pos: Position, end_pos: Position):
        super().__init__(vessel_id, 'yacht', start_pos, end_pos, max_speed=10.0)
        self.is_sailing = True
