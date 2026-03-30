#!/usr/bin/env python3
"""
Download and prepare geospatial datasets

Downloads:
- LandsD 3D-BIT00 elevation data (Victoria Harbour region)
- Open3DHK 3D city model

Note: This is a template. Actual downloads depend on available APIs.
For demonstration, we'll create synthetic data.
"""

import os
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def setup_data_directories():
    """Create data directories if they don't exist"""
    dirs = [
        'data/hko',
        'data/geospatial',
        'data/maritime',
        'output'
    ]

    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        logger.info(f"✓ Created directory: {dir_path}")


def create_sample_landsD_data():
    """
    Create sample LandsD elevation data for Victoria Harbour

    In production, you would download actual data from:
    https://data.gov.hk/en-data/dataset/hk-lands-3d-bit00
    """
    import numpy as np

    logger.info("Creating sample LandsD elevation data...")

    # Victoria Harbour bounds (lat/lon)
    lat_min, lat_max = 22.28, 22.31
    lon_min, lon_max = 114.16, 114.20

    # Create elevation grid (simplified)
    size = 512
    elevation = np.random.uniform(0, 500, (size, size))

    # Add some peaks (buildings, hills)
    elevation[100:150, 100:150] += 300  # Simulated buildings
    elevation[250:300, 200:250] += 250  # Simulated terrain

    # Save as numpy array
    np.save('data/geospatial/landsD_elevation.npy', elevation)
    logger.info("✓ Saved LandsD elevation data (512x512 grid)")

    # Save metadata
    metadata = {
        'bounds': {
            'lat_min': lat_min,
            'lat_max': lat_max,
            'lon_min': lon_min,
            'lon_max': lon_max
        },
        'resolution': 'approximately 20m',
        'source': 'LandsD 3D-BIT00',
        'region': 'Victoria Harbour, Hong Kong'
    }

    with open('data/geospatial/landsD_metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)

    logger.info("✓ Saved metadata")


def create_sample_open3dhk_data():
    """
    Create sample Open3DHK building data

    In production, download from: https://3d.map.gov.hk
    """
    import numpy as np

    logger.info("Creating sample Open3DHK building data...")

    # Sample buildings in Victoria Harbour area
    buildings = []

    # Random buildings
    np.random.seed(42)
    for i in range(50):  # 50 sample buildings
        building = {
            'id': f'building_{i}',
            'latitude': 22.28 + np.random.uniform(0, 0.03),
            'longitude': 114.16 + np.random.uniform(0, 0.04),
            'height': 50 + np.random.uniform(0, 400),  # 50-450 meters
            'floors': int(np.random.uniform(5, 100)),
            'use': np.random.choice(['residential', 'commercial', 'mixed', 'industrial'])
        }
        buildings.append(building)

    # Save as GeoJSON
    geojson = {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'properties': {k: v for k, v in b.items() if k not in ['latitude', 'longitude']},
                'geometry': {
                    'type': 'Point',
                    'coordinates': [b['longitude'], b['latitude']]
                }
            }
            for b in buildings
        ]
    }

    with open('data/geospatial/open3dhk_buildings.geojson', 'w') as f:
        json.dump(geojson, f, indent=2)

    logger.info(f"✓ Created {len(buildings)} sample buildings")


def create_fairways_data():
    """Create Principal Fairways GeoJSON"""
    logger.info("Creating Principal Fairways data...")

    # Victoria Harbour Principal Fairways
    fairways = {
        'Central': {
            'coordinates': [114.175, 22.290],
            'width': 500,
            'depth': 15
        },
        'Eastern': {
            'coordinates': [114.190, 22.287],
            'width': 400,
            'depth': 13
        },
        'Hung_Hom': {
            'coordinates': [114.178, 22.297],
            'width': 350,
            'depth': 12
        },
        'Yau_Ma_Tei': {
            'coordinates': [114.172, 22.302],
            'width': 450,
            'depth': 14
        },
        'Tsim_Sha_Tsui': {
            'coordinates': [114.170, 22.298],
            'width': 380,
            'depth': 11
        }
    }

    features = []
    for name, data in fairways.items():
        feature = {
            'type': 'Feature',
            'properties': {
                'name': name,
                'width_m': data['width'],
                'depth_m': data['depth'],
                'vessel_type': 'all',
                'traffic_direction': 'two-way'
            },
            'geometry': {
                'type': 'Point',
                'coordinates': data['coordinates']
            }
        }
        features.append(feature)

    geojson = {
        'type': 'FeatureCollection',
        'features': features
    }

    with open('data/maritime/principal_fairways.geojson', 'w') as f:
        json.dump(geojson, f, indent=2)

    logger.info(f"✓ Created {len(fairways)} Principal Fairways")


def main():
    """Main download function"""
    print("=" * 70)
    print("Geospatial Data Download & Preparation")
    print("=" * 70)

    print("\n[1] Setting up directories...")
    setup_data_directories()

    print("\n[2] Creating sample LandsD elevation data...")
    create_sample_landsD_data()

    print("\n[3] Creating sample Open3DHK building data...")
    create_sample_open3dhk_data()

    print("\n[4] Creating Principal Fairways data...")
    create_fairways_data()

    print("\n" + "=" * 70)
    print("✓ All geospatial data prepared!")
    print("=" * 70)
    print("\nData location: data/geospatial/")
    print("  - landsD_elevation.npy (elevation grid)")
    print("  - open3dhk_buildings.geojson (building locations)")
    print("  - landsD_metadata.json (metadata)")
    print("\nMaritime data: data/maritime/")
    print("  - principal_fairways.geojson (fairway definitions)")


if __name__ == "__main__":
    main()
