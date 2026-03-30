"""
Agent-Based Maritime Traffic Simulator

Simulates vessel movements through Victoria Harbour with:
- Principal Fairway constraints
- Wind perturbations (from HKO data)
- Collision detection
- Multi-vessel interactions
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import logging
import csv

try:
    from .maritime_agents import VesselAgent, FerryAgent, CargoAgent, YachtAgent, Position
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from maritime_agents import VesselAgent, FerryAgent, CargoAgent, YachtAgent, Position

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MaritimeSimulator:
    """
    Agent-based maritime traffic simulator for Victoria Harbour
    """

    # Victoria Harbour Principal Fairways (simplified bounds)
    PRINCIPAL_FAIRWAYS = {
        'Central': {'lat_min': 22.290, 'lat_max': 22.295, 'lon_min': 114.175, 'lon_max': 114.185},
        'Eastern': {'lat_min': 22.285, 'lat_max': 22.290, 'lon_min': 114.185, 'lon_max': 114.195},
        'Hung_Hom': {'lat_min': 22.295, 'lat_max': 22.300, 'lon_min': 114.175, 'lon_max': 114.185},
        'Yau_Ma_Tei': {'lat_min': 22.300, 'lat_max': 22.305, 'lon_min': 114.170, 'lon_max': 114.180},
        'Tsim_Sha_Tsui': {'lat_min': 22.295, 'lat_max': 22.300, 'lon_min': 114.165, 'lon_max': 114.175},
    }

    def __init__(self, start_time: datetime = None, end_time: datetime = None,
                 wind_data: pd.DataFrame = None):
        """
        Initialize simulator

        Args:
            start_time: Simulation start time
            end_time: Simulation end time
            wind_data: DataFrame with wind speed and direction
        """
        self.start_time = start_time or datetime.now()
        self.end_time = end_time or (self.start_time + timedelta(hours=24))
        self.wind_data = wind_data if wind_data is not None else pd.DataFrame()
        self.current_time = self.start_time

        self.vessels: List[VesselAgent] = []
        self.dt = 60  # Time step in seconds (1 minute)
        self.simulation_data = []

        logger.info(f"Simulator initialized: {self.start_time} to {self.end_time}")

    def add_vessel(self, vessel_id: str, vessel_type: str,
                   start_pos: Tuple[float, float], end_pos: Tuple[float, float],
                   schedule: List = None) -> None:
        """
        Add vessel to simulation

        Args:
            vessel_id: Unique ID
            vessel_type: 'ferry', 'cargo', 'yacht'
            start_pos: (latitude, longitude)
            end_pos: (latitude, longitude)
            schedule: Optional schedule for ferries
        """
        start = Position(lat=start_pos[0], lon=start_pos[1])
        end = Position(lat=end_pos[0], lon=end_pos[1])

        if vessel_type == 'ferry':
            vessel = FerryAgent(vessel_id, start, end, schedule)
        elif vessel_type == 'cargo':
            vessel = CargoAgent(vessel_id, start, end)
        elif vessel_type == 'yacht':
            vessel = YachtAgent(vessel_id, start, end)
        else:
            vessel = VesselAgent(vessel_id, vessel_type, start, end)

        self.vessels.append(vessel)
        logger.info(f"Added {vessel_type} vessel: {vessel_id}")

    def _get_wind_at_time(self, timestamp: datetime) -> Dict:
        """
        Get wind data for given timestamp

        Returns:
            Dict with 'speed' (m/s) and 'direction' (degrees)
        """
        if self.wind_data.empty:
            # Default wind if no data provided
            return {
                'speed': 5.0 + 2.0 * np.sin(timestamp.timestamp() / 3600),
                'direction': 180 + 30 * np.sin(timestamp.timestamp() / 7200)
            }

        # Find nearest wind data point
        if 'timestamp' in self.wind_data.columns:
            self.wind_data['timestamp'] = pd.to_datetime(self.wind_data['timestamp'])
            idx = (self.wind_data['timestamp'] - timestamp).abs().argmin()
            row = self.wind_data.iloc[idx]
            return {
                'speed': float(row.get('wind_speed', 5.0)),
                'direction': float(row.get('wind_direction', 180))
            }

        return {'speed': 5.0, 'direction': 180}

    def _check_collisions(self) -> None:
        """Check for vessel-to-vessel collisions"""
        min_distance = 500  # meters

        for i, v1 in enumerate(self.vessels):
            for v2 in self.vessels[i+1:]:
                if v1.active and v2.active:
                    dist = v1.distance_to_vessel(v2)
                    if dist < min_distance:
                        v1.set_collision_risk(True)
                        v2.set_collision_risk(True)
                        logger.warning(f"Collision risk: {v1.vessel_id} <-> {v2.vessel_id} ({dist:.0f}m)")

    def _check_fairway_violations(self) -> None:
        """Check if vessels are within fairway bounds"""
        for vessel in self.vessels:
            if vessel.active:
                # Check against multiple fairways
                for fairway_name, bounds in self.PRINCIPAL_FAIRWAYS.items():
                    if vessel.check_fairway_boundary(bounds):
                        break

    def step(self) -> None:
        """
        Execute one simulation timestep
        """
        # Get wind data for current time
        wind = self._get_wind_at_time(self.current_time)

        # Update all vessel positions
        for vessel in self.vessels:
            if vessel.active:
                vessel.update_position(self.dt, wind)

        # Check for collisions and fairway violations
        self._check_collisions()
        self._check_fairway_violations()

        # Record simulation state
        self._record_state()

        # Advance time
        self.current_time += timedelta(seconds=self.dt)

    def _record_state(self) -> None:
        """Record current simulation state"""
        timestamp = self.current_time.isoformat()

        for vessel in self.vessels:
            state = vessel.get_state()
            state['timestamp'] = timestamp
            state['wind_speed'] = self._get_wind_at_time(self.current_time)['speed']
            self.simulation_data.append(state)

    def run(self, show_progress: bool = True) -> pd.DataFrame:
        """
        Run simulation from start_time to end_time

        Args:
            show_progress: Print progress updates

        Returns:
            DataFrame with simulation results
        """
        num_steps = int((self.end_time - self.start_time).total_seconds() / self.dt)
        logger.info(f"Running {num_steps} timesteps...")

        for step in range(num_steps):
            self.step()

            if show_progress and step % 60 == 0:  # Print every minute
                print(f"  Simulated {step}/{num_steps} timesteps "
                      f"({100*step/num_steps:.1f}%) - {self.current_time}")

        logger.info("Simulation complete")
        return self.get_results_dataframe()

    def get_results_dataframe(self) -> pd.DataFrame:
        """Convert simulation data to DataFrame"""
        return pd.DataFrame(self.simulation_data)

    def save_results(self, filepath: str) -> None:
        """Save results to CSV"""
        df = self.get_results_dataframe()
        df.to_csv(filepath, index=False)
        logger.info(f"Saved {len(df)} records to {filepath}")

    def get_fairway_occupancy(self) -> Dict:
        """Calculate fairway occupancy statistics"""
        df = self.get_results_dataframe()
        occupancy = {}

        for fairway in self.PRINCIPAL_FAIRWAYS.keys():
            count = len(df[df['in_fairway']])
            occupancy[fairway] = count

        return occupancy


# Example usage
if __name__ == "__main__":
    print("=" * 70)
    print("Maritime Traffic Simulator - Victoria Harbour")
    print("=" * 70)

    # Create simulator
    sim = MaritimeSimulator(
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(hours=24)
    )

    # Add sample vessels (Hong Kong routes)
    print("\n[1] Adding sample vessels...")

    # Star Ferry (Kowloon <-> Central)
    for i in range(3):
        sim.add_vessel(
            vessel_id=f'StarFerry_{i}',
            vessel_type='ferry',
            start_pos=(22.295, 114.170),  # Tsim Sha Tsui
            end_pos=(22.285, 114.180)      # Central
        )

    # Cargo ships
    for i in range(2):
        sim.add_vessel(
            vessel_id=f'Cargo_{i}',
            vessel_type='cargo',
            start_pos=(22.300, 114.165),
            end_pos=(22.280, 114.190)
        )

    # Yachts
    for i in range(3):
        sim.add_vessel(
            vessel_id=f'Yacht_{i}',
            vessel_type='yacht',
            start_pos=(22.290, 114.175),
            end_pos=(22.293, 114.188)
        )

    print(f"✓ Added {len(sim.vessels)} vessels")

    # Run simulation
    print("\n[2] Running 24-hour simulation...")
    results = sim.run(show_progress=True)

    # Save results
    print(f"\n[3] Saving results...")
    import os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(_root, "output", "maritime_baseline_24h.csv")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sim.save_results(output_path)

    # Print statistics
    print(f"\n[4] Simulation Statistics:")
    print(f"   - Total records: {len(results)}")
    print(f"   - Time period: {sim.start_time} to {sim.end_time}")
    print(f"   - Vessels simulated: {len(sim.vessels)}")
    print(f"   - Timestep: {sim.dt} seconds")
    print(f"   - Collision incidents: {len(results[results['collision_risk']])}")

    print("\n" + "=" * 70)
    print(f"✓ Results saved to: {output_path}")
    print("=" * 70)
