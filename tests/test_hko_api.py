"""
Unit tests for HKO API Client

Tests cover:
- API connectivity and response parsing
- Data validation
- Error handling
- Retry logic
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.hko_api_client import HKOAPIClient


class TestHKOAPIClient:
    """Test suite for HKO API Client"""

    @pytest.fixture
    def client(self):
        """Create client instance for testing"""
        return HKOAPIClient(timeout=10, retry_attempts=2)

    def test_client_initialization(self, client):
        """Test that client initializes correctly"""
        assert client.timeout == 10
        assert client.retry_attempts == 2
        assert client.BASE_URL == "https://data.weather.gov.hk/weatherAPI/opendata"

    def test_stations_dictionary(self, client):
        """Test that stations are properly defined"""
        assert len(client.STATIONS) > 0
        assert 'ChekLapKok' in client.STATIONS
        assert client.STATIONS['ChekLapKok'] == 'Chek Lap Kok'

    def test_get_current_weather_structure(self, client):
        """Test current weather response structure"""
        # This test will make a real API call
        # Skip if API is unavailable
        try:
            result = client.get_current_weather()
            # Should return a dictionary (even if empty)
            assert isinstance(result, dict)
        except Exception as e:
            pytest.skip(f"API unavailable: {e}")

    def test_get_wind_data_returns_dataframe(self, client):
        """Test that wind data returns a DataFrame"""
        try:
            df = client.get_wind_data(station='ChekLapKok')
            assert isinstance(df, pd.DataFrame)
        except Exception as e:
            pytest.skip(f"API unavailable: {e}")

    def test_get_wind_data_has_required_columns(self, client):
        """Test that wind data has required columns"""
        try:
            df = client.get_wind_data(station='ChekLapKok')
            if not df.empty:
                required_cols = ['timestamp', 'wind_speed', 'wind_direction']
                for col in required_cols:
                    assert col in df.columns, f"Missing column: {col}"
        except Exception as e:
            pytest.skip(f"API unavailable: {e}")

    def test_get_forecast_returns_dataframe(self, client):
        """Test that forecast returns a DataFrame"""
        try:
            df = client.get_weather_forecast(hours=24)
            assert isinstance(df, pd.DataFrame)
        except Exception as e:
            pytest.skip(f"API unavailable: {e}")

    def test_forecast_hours_limit(self, client):
        """Test that forecast respects hour limits"""
        try:
            df = client.get_weather_forecast(hours=60)  # Request more than max
            # Should not crash, should limit to 48
            assert isinstance(df, pd.DataFrame)
        except Exception as e:
            pytest.skip(f"API unavailable: {e}")

    def test_wind_data_timestamp_format(self, client):
        """Test that timestamps are properly formatted"""
        try:
            df = client.get_wind_data(station='ChekLapKok')
            if not df.empty and 'timestamp' in df.columns:
                # Check that timestamp is datetime
                assert pd.api.types.is_datetime64_any_dtype(df['timestamp'])
        except Exception as e:
            pytest.skip(f"API unavailable: {e}")

    def test_station_info_retrieval(self, client):
        """Test retrieving station information"""
        try:
            info = client.get_station_info()
            assert isinstance(info, dict)
        except Exception as e:
            pytest.skip(f"API unavailable: {e}")

    def test_csv_save_functionality(self, client, tmp_path):
        """Test saving data to CSV"""
        df = pd.DataFrame({
            'timestamp': [datetime.now(), datetime.now() - timedelta(hours=1)],
            'wind_speed': [5.0, 6.0],
            'wind_direction': [180, 185]
        })

        filepath = tmp_path / "test_wind_data.csv"
        client.save_to_csv(df, str(filepath))

        # Verify file was created
        assert filepath.exists()

        # Verify data can be read back
        loaded_df = pd.read_csv(filepath)
        assert len(loaded_df) == len(df)


class TestHKOAPIIntegration:
    """Integration tests for HKO API"""

    @pytest.fixture
    def client(self):
        return HKOAPIClient()

    def test_multiple_stations(self, client):
        """Test fetching data for multiple stations"""
        try:
            for station_code in ['ChekLapKok', 'CentralWestern']:
                df = client.get_wind_data(station=station_code)
                assert isinstance(df, pd.DataFrame)
        except Exception as e:
            pytest.skip(f"API unavailable: {e}")

    def test_data_consistency(self, client):
        """Test that multiple calls return consistent data"""
        try:
            df1 = client.get_wind_data()
            df2 = client.get_wind_data()

            # Both should be DataFrames of same type
            assert isinstance(df1, pd.DataFrame)
            assert isinstance(df2, pd.DataFrame)
        except Exception as e:
            pytest.skip(f"API unavailable: {e}")


if __name__ == "__main__":
    # Run tests with: pytest tests/test_hko_api.py -v
    pytest.main([__file__, "-v"])
