"""
Tests for maritime_agents, maritime_simulator, and collision_detection modules
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from src.maritime_agents import Position, VesselAgent, FerryAgent, CargoAgent, YachtAgent
from src.maritime_simulator import MaritimeSimulator
from src.collision_detection import CollisionDetector, FairwayMonitor


# ─── Position Tests ────────────────────────────────────────────────────────────

class TestPosition:
    def test_distance_same_point(self):
        p = Position(lat=22.295, lon=114.175)
        assert p.distance_to(p) == pytest.approx(0.0)

    def test_distance_known_separation(self):
        # ~1 degree latitude ≈ 111000 m
        p1 = Position(lat=22.0, lon=114.0)
        p2 = Position(lat=23.0, lon=114.0)
        assert p1.distance_to(p2) == pytest.approx(111000, rel=0.02)

    def test_distance_symmetric(self):
        # The formula uses self.lat for the lon cosine factor, so results differ
        # by < 0.1% over the Victoria Harbour area (~0.01 degree latitude range)
        p1 = Position(lat=22.290, lon=114.170)
        p2 = Position(lat=22.300, lon=114.180)
        assert p1.distance_to(p2) == pytest.approx(p2.distance_to(p1), rel=0.01)


# ─── VesselAgent Tests ─────────────────────────────────────────────────────────

class TestVesselAgent:
    @pytest.fixture
    def vessel(self):
        start = Position(lat=22.295, lon=114.170)
        end = Position(lat=22.285, lon=114.180)
        return VesselAgent("test_01", "ferry", start, end)

    def test_initial_state(self, vessel):
        assert vessel.vessel_id == "test_01"
        assert vessel.vessel_type == "ferry"
        assert vessel.active is True
        assert vessel.collision_risk is False
        assert vessel.in_fairway is False

    def test_get_state_keys(self, vessel):
        state = vessel.get_state()
        for key in ('vessel_id', 'vessel_type', 'latitude', 'longitude',
                    'speed', 'heading', 'active', 'in_fairway', 'collision_risk'):
            assert key in state

    def test_position_updates_after_step(self, vessel):
        lat_before = vessel.position.lat
        lon_before = vessel.position.lon
        vessel.update_position(dt=60, wind_data={'speed': 5.0, 'direction': 180})
        assert (vessel.position.lat != lat_before or vessel.position.lon != lon_before)

    def test_vessel_deactivates_at_destination(self):
        start = Position(lat=22.295, lon=114.170)
        end = Position(lat=22.295, lon=114.170)  # same point
        v = VesselAgent("close_01", "cargo", start, end)
        v.update_position(dt=60)
        assert v.active is False

    def test_set_collision_risk(self, vessel):
        vessel.set_collision_risk(True)
        assert vessel.collision_risk is True

    def test_fairway_boundary_inside(self, vessel):
        bounds = {'lat_min': 22.29, 'lat_max': 22.30,
                  'lon_min': 114.16, 'lon_max': 114.18}
        result = vessel.check_fairway_boundary(bounds)
        assert result is True
        assert vessel.in_fairway is True

    def test_fairway_boundary_outside(self, vessel):
        bounds = {'lat_min': 22.30, 'lat_max': 22.31,
                  'lon_min': 114.20, 'lon_max': 114.22}
        result = vessel.check_fairway_boundary(bounds)
        assert result is False

    def test_distance_to_vessel(self, vessel):
        other = VesselAgent("other_01", "cargo",
                            Position(lat=22.295, lon=114.170),
                            Position(lat=22.285, lon=114.180))
        assert vessel.distance_to_vessel(other) == pytest.approx(0.0, abs=1.0)


# ─── Vessel Subclass Tests ─────────────────────────────────────────────────────

class TestVesselSubclasses:
    def test_ferry_max_speed(self):
        f = FerryAgent("f1", Position(22.295, 114.170), Position(22.285, 114.180))
        assert f.max_speed == 12.0
        assert f.vessel_type == "ferry"

    def test_cargo_max_speed(self):
        c = CargoAgent("c1", Position(22.295, 114.170), Position(22.285, 114.180))
        assert c.max_speed == 7.0
        assert c.cargo_weight == 10000

    def test_yacht_max_speed(self):
        y = YachtAgent("y1", Position(22.295, 114.170), Position(22.285, 114.180))
        assert y.max_speed == 10.0
        assert y.is_sailing is True


# ─── MaritimeSimulator Tests ───────────────────────────────────────────────────

class TestMaritimeSimulator:
    @pytest.fixture
    def sim(self):
        start = datetime(2026, 3, 30, 0, 0, 0)
        return MaritimeSimulator(start_time=start,
                                 end_time=start + timedelta(hours=1))

    def test_initialization(self, sim):
        assert len(sim.vessels) == 0
        assert sim.dt == 60

    def test_add_vessel_types(self, sim):
        sim.add_vessel("f1", "ferry", (22.295, 114.170), (22.285, 114.180))
        sim.add_vessel("c1", "cargo", (22.300, 114.165), (22.280, 114.190))
        sim.add_vessel("y1", "yacht", (22.290, 114.175), (22.293, 114.188))
        assert len(sim.vessels) == 3

    def test_run_returns_dataframe(self, sim):
        sim.add_vessel("f1", "ferry", (22.295, 114.170), (22.285, 114.180))
        df = sim.run(show_progress=False)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_results_have_required_columns(self, sim):
        sim.add_vessel("f1", "ferry", (22.295, 114.170), (22.285, 114.180))
        df = sim.run(show_progress=False)
        for col in ('vessel_id', 'vessel_type', 'latitude', 'longitude',
                    'timestamp', 'collision_risk', 'in_fairway'):
            assert col in df.columns

    def test_wind_data_applied(self, sample_wind_data):
        start = datetime(2026, 3, 30, 0, 0, 0)
        sim = MaritimeSimulator(start_time=start,
                                end_time=start + timedelta(minutes=5),
                                wind_data=sample_wind_data)
        sim.add_vessel("f1", "ferry", (22.295, 114.170), (22.285, 114.180))
        df = sim.run(show_progress=False)
        assert len(df) > 0

    def test_save_results(self, sim, tmp_path):
        sim.add_vessel("f1", "ferry", (22.295, 114.170), (22.285, 114.180))
        sim.run(show_progress=False)
        out = tmp_path / "test_output.csv"
        sim.save_results(str(out))
        assert out.exists()
        loaded = pd.read_csv(out)
        assert len(loaded) > 0


# ─── CollisionDetector Tests ───────────────────────────────────────────────────

class TestCollisionDetector:
    def test_collision_detected_when_close(self):
        detector = CollisionDetector(min_distance=500)
        v1 = VesselAgent("v1", "ferry", Position(22.295, 114.170), Position(22.285, 114.180))
        v2 = VesselAgent("v2", "cargo", Position(22.295, 114.170), Position(22.285, 114.180))
        assert detector.check_vessel_collision(v1, v2) is True

    def test_no_collision_when_far(self):
        detector = CollisionDetector(min_distance=500)
        v1 = VesselAgent("v1", "ferry", Position(22.290, 114.170), Position(22.285, 114.180))
        v2 = VesselAgent("v2", "cargo", Position(22.310, 114.190), Position(22.285, 114.180))
        assert detector.check_vessel_collision(v1, v2) is False

    def test_collision_events_recorded(self):
        detector = CollisionDetector(min_distance=500)
        v1 = VesselAgent("v1", "ferry", Position(22.295, 114.170), Position(22.285, 114.180))
        v2 = VesselAgent("v2", "cargo", Position(22.295, 114.170), Position(22.285, 114.180))
        detector.check_vessel_collision(v1, v2)
        events = detector.get_collision_events()
        assert len(events) == 1
        assert events[0]['vessel1'] == 'v1'
        assert events[0]['vessel2'] == 'v2'

    def test_fairway_violation(self):
        detector = CollisionDetector()
        v = VesselAgent("v1", "ferry", Position(22.292, 114.178), Position(22.285, 114.180))
        bounds = {'lat_min': 22.290, 'lat_max': 22.295,
                  'lon_min': 114.175, 'lon_max': 114.185}
        assert detector.check_fairway_violation(v, bounds) is True


# ─── FairwayMonitor Tests ──────────────────────────────────────────────────────

class TestFairwayMonitor:
    FAIRWAYS = {
        'Central': {'lat_min': 22.290, 'lat_max': 22.295,
                    'lon_min': 114.175, 'lon_max': 114.185},
        'Eastern': {'lat_min': 22.285, 'lat_max': 22.290,
                    'lon_min': 114.185, 'lon_max': 114.195},
    }

    def test_occupancy_empty(self):
        monitor = FairwayMonitor(self.FAIRWAYS)
        occupancy = monitor.get_occupancy([])
        assert all(v == 0 for v in occupancy.values())

    def test_occupancy_counts_vessel_in_fairway(self):
        monitor = FairwayMonitor(self.FAIRWAYS)
        v = VesselAgent("v1", "ferry", Position(22.292, 114.178), Position(22.285, 114.180))
        occupancy = monitor.get_occupancy([v])
        assert occupancy['Central'] == 1
        assert occupancy['Eastern'] == 0

    def test_bottleneck_detection(self):
        monitor = FairwayMonitor(self.FAIRWAYS)
        occupancy = {'Central': 6, 'Eastern': 2}
        bottlenecks = monitor.get_bottleneck_fairways(occupancy, threshold=5)
        assert 'Central' in bottlenecks
        assert 'Eastern' not in bottlenecks
