"""
Tests for geospatial_loader module
"""

import pytest
import numpy as np
import json
from pathlib import Path

from src.geospatial_loader import GeospatialLoader


class TestGeospatialLoader:
    def test_initialization(self, tmp_path):
        loader = GeospatialLoader(data_dir=str(tmp_path))
        assert loader.crs == 'EPSG:2326'
        assert loader.elevation_data is None
        assert loader.buildings_data is None
        assert loader.fairways_data is None

    def test_load_elevation_missing_file(self, tmp_path):
        loader = GeospatialLoader(data_dir=str(tmp_path))
        result = loader.load_landsD_elevation()
        assert result is None

    def test_load_buildings_missing_file(self, tmp_path):
        loader = GeospatialLoader(data_dir=str(tmp_path))
        result = loader.load_open3dhk_buildings()
        assert result is None

    def test_load_fairways_missing_file(self, tmp_path):
        loader = GeospatialLoader(data_dir=str(tmp_path))
        result = loader.load_fairways()
        assert result is None

    def test_validate_crs_hk1980(self, tmp_path):
        loader = GeospatialLoader(data_dir=str(tmp_path))
        assert loader.validate_crs() is True

    def test_validate_crs_wrong(self, tmp_path):
        loader = GeospatialLoader(data_dir=str(tmp_path))
        loader.crs = 'EPSG:4326'
        assert loader.validate_crs() is False

    def test_load_elevation_from_file(self, tmp_path):
        geo_dir = tmp_path / 'geospatial'
        geo_dir.mkdir()
        data = np.random.rand(100, 100).astype(np.float32)
        np.save(geo_dir / 'landsD_elevation.npy', data)

        loader = GeospatialLoader(data_dir=str(tmp_path))
        result = loader.load_landsD_elevation()
        assert result is not None
        assert result.shape == (100, 100)

    def test_load_buildings_from_file(self, tmp_path):
        geo_dir = tmp_path / 'geospatial'
        geo_dir.mkdir()
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature",
                 "geometry": {"type": "Point", "coordinates": [114.175, 22.292]},
                 "properties": {"id": "B001", "height": 50}}
            ]
        }
        (geo_dir / 'open3dhk_buildings.geojson').write_text(json.dumps(geojson_data))

        loader = GeospatialLoader(data_dir=str(tmp_path))
        result = loader.load_open3dhk_buildings()
        assert result is not None
        assert len(result['features']) == 1

    def test_load_fairways_from_file(self, tmp_path):
        maritime_dir = tmp_path / 'maritime'
        maritime_dir.mkdir()
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature",
                 "geometry": {"type": "Polygon", "coordinates": [[[114.17, 22.29], [114.18, 22.29], [114.18, 22.30], [114.17, 22.30], [114.17, 22.29]]]},
                 "properties": {"name": "Central Fairway"}}
            ]
        }
        (maritime_dir / 'principal_fairways.geojson').write_text(json.dumps(geojson_data))

        loader = GeospatialLoader(data_dir=str(tmp_path))
        result = loader.load_fairways()
        assert result is not None
        assert len(result['features']) == 1

    def test_get_elevation_at_point_no_data(self, tmp_path):
        loader = GeospatialLoader(data_dir=str(tmp_path))
        result = loader.get_elevation_at_point(22.295, 114.175)
        assert result is None

    def test_get_elevation_at_point_with_data(self, tmp_path):
        geo_dir = tmp_path / 'geospatial'
        geo_dir.mkdir()
        data = np.ones((100, 100), dtype=np.float32) * 42.0
        np.save(geo_dir / 'landsD_elevation.npy', data)

        loader = GeospatialLoader(data_dir=str(tmp_path))
        loader.load_landsD_elevation()
        result = loader.get_elevation_at_point(22.295, 114.175)
        assert result == pytest.approx(42.0)

    def test_get_buildings_in_region_no_data(self, tmp_path):
        loader = GeospatialLoader(data_dir=str(tmp_path))
        result = loader.get_buildings_in_region((22.28, 22.31), (114.16, 114.20))
        assert result == []

    def test_spatial_index_no_buildings(self, tmp_path):
        loader = GeospatialLoader(data_dir=str(tmp_path))
        # Should not raise
        loader.create_spatial_index()
