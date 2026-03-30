"""
Collision Detection and Fairway Monitoring

Detects:
- Vessel-to-vessel collisions
- Fairway boundary violations
- High-risk zones
"""

import numpy as np
from typing import List, Tuple, Dict
import logging

logger = logging.getLogger(__name__)


class CollisionDetector:
    """
    Detects collisions between vessels and fairway violations
    """

    def __init__(self, min_distance: float = 500.0):
        """
        Initialize collision detector

        Args:
            min_distance: Minimum safe distance between vessels (meters)
        """
        self.min_distance = min_distance
        self.collision_events = []

    def check_vessel_collision(self, vessel1, vessel2) -> bool:
        """
        Check if two vessels are in collision/risk

        Args:
            vessel1: First vessel agent
            vessel2: Second vessel agent

        Returns:
            True if collision risk exists
        """
        distance = vessel1.distance_to_vessel(vessel2)

        if distance < self.min_distance:
            self.collision_events.append({
                'vessel1': vessel1.vessel_id,
                'vessel2': vessel2.vessel_id,
                'distance': distance,
                'timestamp': vessel1.position.lat  # Placeholder
            })
            return True

        return False

    def check_fairway_violation(self, vessel, fairway_bounds: Dict) -> bool:
        """
        Check if vessel violates fairway boundaries

        Args:
            vessel: Vessel agent
            fairway_bounds: Dict with lat/lon min/max

        Returns:
            True if violation detected
        """
        return vessel.check_fairway_boundary(fairway_bounds)

    def get_collision_events(self) -> List[Dict]:
        """Return list of collision events"""
        return self.collision_events


class FairwayMonitor:
    """
    Monitors occupancy and traffic flow in fairways
    """

    def __init__(self, fairway_definitions: Dict):
        """
        Initialize fairway monitor

        Args:
            fairway_definitions: Dict of fairway bounds
        """
        self.fairways = fairway_definitions
        self.occupancy_history = {}

    def get_occupancy(self, vessels: List) -> Dict:
        """
        Get current occupancy for all fairways

        Args:
            vessels: List of vessel agents

        Returns:
            Dict with occupancy counts per fairway
        """
        occupancy = {name: 0 for name in self.fairways.keys()}

        for vessel in vessels:
            if not vessel.active:
                continue

            for fairway_name, bounds in self.fairways.items():
                if vessel.check_fairway_boundary(bounds):
                    occupancy[fairway_name] += 1
                    break

        return occupancy

    def get_bottleneck_fairways(self, occupancy: Dict, threshold: int = 5) -> List[str]:
        """
        Identify bottleneck fairways (high occupancy)

        Args:
            occupancy: Occupancy dict
            threshold: Occupancy threshold for bottleneck

        Returns:
            List of bottleneck fairway names
        """
        return [name for name, count in occupancy.items() if count >= threshold]
