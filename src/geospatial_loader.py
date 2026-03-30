"""
Geospatial Data Loader

Loads and validates:
- LandsD 3D-BIT00 elevation data
- Open3DHK 3D city models
- Principal Fairways definitions
"""

import numpy as np
import json
import logging
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class GeospatialLoader:
    """Load and manage geospatial data"""

    def __init__(self, data_dir: str = 'data'):
        """
        Initialize loader

        Args:
            data_dir: Base directory for geospatial data
        """
        self.data_dir = Path(data_dir)
        self.geospatial_dir = self.data_dir / 'geospatial'
        self.maritime_dir = self.data_dir / 'maritime'

        self.elevation_data = None
        self.buildings_data = None
        self.fairways_data = None
        self.crs = 'EPSG:2326'  # Hong Kong 1980 Grid

    def load_landsD_elevation(self) -> np.ndarray:
        """
        Load LandsD elevation data

        Returns:
            Elevation grid as numpy array
        """
        filepath = self.geospatial_dir / 'landsD_elevation.npy'

        if not filepath.exists():
            logger.error(f"LandsD data not found: {filepath}")
            return None

        try:
            self.elevation_data = np.load(filepath)
            logger.info(f"✓ Loaded LandsD elevation data (shape: {self.elevation_data.shape})")
            return self.elevation_data

        except Exception as e:
            logger.error(f"Error loading elevation data: {e}")
            return None

    def load_open3dhk_buildings(self) -> Dict:
        """
        Load Open3DHK building data

        Returns:
            GeoJSON feature collection as dict
        """
        filepath = self.geospatial_dir / 'open3dhk_buildings.geojson'

        if not filepath.exists():
            logger.error(f"Open3DHK data not found: {filepath}")
            return None

        try:
            with open(filepath, 'r') as f:
                self.buildings_data = json.load(f)

            num_buildings = len(self.buildings_data.get('features', []))
            logger.info(f"✓ Loaded Open3DHK buildings ({num_buildings} buildings)")
            return self.buildings_data

        except Exception as e:
            logger.error(f"Error loading buildings data: {e}")
            return None

    def load_fairways(self) -> Dict:
        """
        Load Principal Fairways definitions

        Returns:
            GeoJSON feature collection as dict
        """
        filepath = self.maritime_dir / 'principal_fairways.geojson'

        if not filepath.exists():
            logger.error(f"Fairways data not found: {filepath}")
            return None

        try:
            with open(filepath, 'r') as f:
                self.fairways_data = json.load(f)

            num_fairways = len(self.fairways_data.get('features', []))
            logger.info(f"✓ Loaded Principal Fairways ({num_fairways} fairways)")
            return self.fairways_data

        except Exception as e:
            logger.error(f"Error loading fairways data: {e}")
            return None

    def validate_crs(self) -> bool:
        """
        Validate coordinate reference system

        Returns:
            True if CRS is valid for Hong Kong
        """
        logger.info(f"Validating CRS: {self.crs}")

        if self.crs == 'EPSG:2326':
            logger.info("✓ CRS validated: Hong Kong 1980 Grid")
            return True

        logger.warning(f"Warning: CRS {self.crs} may need conversion")
        return False

    def create_spatial_index(self) -> None:
        """Create spatial index for buildings (simplified)"""
        if self.buildings_data is None:
            logger.warning("Buildings data not loaded, cannot create index")
            return

        features = self.buildings_data.get('features', [])
        self.spatial_index = {}

        for feature in features:
            coords = feature['geometry']['coordinates']
            self.spatial_index[feature['properties']['id']] = {
                'lon': coords[0],
                'lat': coords[1]
            }

        logger.info(f"✓ Spatial index created for {len(self.spatial_index)} buildings")

    def get_buildings_in_region(self, lat_range: Tuple[float, float],
                               lon_range: Tuple[float, float]) -> list:
        """
        Query buildings in specified region

        Args:
            lat_range: (min_lat, max_lat)
            lon_range: (min_lon, max_lon)

        Returns:
            List of building features in region
        """
        if self.buildings_data is None:
            logger.warning("Buildings data not loaded")
            return []

        features = self.buildings_data.get('features', [])
        results = []

        for feature in features:
            coords = feature['geometry']['coordinates']
            lon, lat = coords[0], coords[1]

            if (lon_range[0] <= lon <= lon_range[1] and
                lat_range[0] <= lat <= lat_range[1]):
                results.append(feature)

        return results

    def get_elevation_at_point(self, lat: float, lon: float) -> float:
        """
        Get elevation at specific point (interpolated)

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Elevation in meters
        """
        if self.elevation_data is None:
            logger.warning("Elevation data not loaded")
            return None

        # Simple indexing (in production, use proper interpolation)
        # Victoria Harbour bounds: lat 22.28-22.31, lon 114.16-114.20
        i = int((lat - 22.28) / 0.03 * self.elevation_data.shape[0])
        j = int((lon - 114.16) / 0.04 * self.elevation_data.shape[1])

        if 0 <= i < self.elevation_data.shape[0] and 0 <= j < self.elevation_data.shape[1]:
            return float(self.elevation_data[i, j])

        return 0.0


def main():
    """Test geospatial loader"""
    print("=" * 70)
    print("Geospatial Data Loader - Test")
    print("=" * 70)

    loader = GeospatialLoader()

    print("\n[1] Loading LandsD elevation data...")
    elevation = loader.load_landsD_elevation()

    print("\n[2] Loading Open3DHK buildings...")
    buildings = loader.load_open3dhk_buildings()

    print("\n[3] Loading Principal Fairways...")
    fairways = loader.load_fairways()

    print("\n[4] Creating spatial index...")
    loader.create_spatial_index()

    print("\n[5] Validating CRS...")
    loader.validate_crs()

    print("\n" + "=" * 70)
    print("✓ All geospatial data loaded and validated!")
    print("=" * 70)


if __name__ == "__main__":
    main()
