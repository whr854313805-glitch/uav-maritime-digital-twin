"""
Pytest configuration and fixtures for the test suite

Defines:
- Logging setup
- Temporary directories
- Common fixtures
- Test markers
"""

import pytest
import logging
import sys
import os
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging for tests
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Define test markers
def pytest_configure(config):
    """Register custom pytest markers"""
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test (requires API access)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "requires_api: mark test as requiring external API access"
    )


@pytest.fixture(scope="session")
def project_root():
    """Return project root directory"""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def data_dir():
    """Return test data directory"""
    data_dir = PROJECT_ROOT / "tests" / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


@pytest.fixture(scope="session")
def output_dir(tmp_path_factory):
    """Create temporary output directory for test results"""
    return tmp_path_factory.mktemp("output")


@pytest.fixture
def sample_wind_data():
    """Sample wind data for testing"""
    import pandas as pd
    from datetime import datetime, timedelta

    data = {
        'timestamp': [datetime.now() - timedelta(hours=i) for i in range(10)],
        'wind_speed': [5.0 + i*0.5 for i in range(10)],
        'wind_direction': [180 + i*5 for i in range(10)],
        'station': ['ChekLapKok'] * 10
    }
    return pd.DataFrame(data)


@pytest.fixture
def logger():
    """Return configured logger for tests"""
    return logging.getLogger("test")


# Skip markers for optional dependencies
@pytest.fixture(scope="session", autouse=True)
def check_dependencies():
    """Check that all required dependencies are available"""
    required = ['numpy', 'pandas', 'requests', 'geopandas']
    missing = []

    for package in required:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    if missing:
        pytest.skip(f"Missing required packages: {', '.join(missing)}")
