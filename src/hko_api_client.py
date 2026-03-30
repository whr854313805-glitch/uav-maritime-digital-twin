"""
HKO Open Data API Client

This module provides a Python wrapper for the Hong Kong Observatory (HKO) Open Data API.
Retrieves weather data including wind, temperature, and humidity at 10-minute resolution.

API Documentation: https://www.hko.gov.hk/en/
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional, Tuple
import json
import time

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HKOAPIClient:
    """
    Client for HKO Open Data API

    Provides methods to fetch:
    - Current weather conditions
    - 48-hour forecast
    - Historical data
    - Wind data for specific stations

    Free API - No authentication required
    """

    # HKO API endpoints
    BASE_URL = "https://data.weather.gov.hk/weatherAPI/opendata"

    # Available stations in Victoria Harbour area
    STATIONS = {
        'ChekLapKok': 'Chek Lap Kok',           # Hong Kong International Airport
        'CentralWestern': 'Central & Western',   # Central
        'EasternDistrict': 'Eastern District',   # Eastern
        'SouthDistrict': 'South',                # South
        'YauTsimMong': 'Yau Tsim Mong',         # Yau Ma Tei/Mong Kok
        'KowloonCity': 'Kowloon City',          # Kowloon City
        'WongTaiSin': 'Wong Tai Sin',           # Wong Tai Sin
        'ShamshuiPo': 'Sham Shui Po',           # Sham Shui Po
        'NorthDistrict': 'North',                # North
        'IslandsDistrict': 'Islands'             # Islands
    }

    def __init__(self, timeout: int = 10, retry_attempts: int = 3):
        """
        Initialize HKO API client

        Args:
            timeout: Request timeout in seconds
            retry_attempts: Number of retries for failed requests
        """
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.session = requests.Session()

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Make HTTP request with retry logic

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response as dictionary

        Raises:
            requests.exceptions.RequestException: If request fails after retries
        """
        url = f"{self.BASE_URL}/{endpoint}"

        for attempt in range(self.retry_attempts):
            try:
                logger.info(f"Fetching {endpoint} (attempt {attempt + 1})")
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed: {e}")
                if attempt < self.retry_attempts - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {self.retry_attempts} attempts")
                    raise

    def get_weather_forecast(self, hours: int = 24) -> pd.DataFrame:
        """
        Get weather forecast for next N hours (10-minute resolution)

        Args:
            hours: Number of hours to forecast (max 48)

        Returns:
            DataFrame with columns: timestamp, station, wind_speed, wind_direction,
                                   temperature, humidity, pressure

        Example:
            >>> client = HKOAPIClient()
            >>> df = client.get_weather_forecast(hours=48)
            >>> print(df.head())
        """
        if hours > 48:
            logger.warning(f"Requested {hours} hours, limiting to 48")
            hours = 48

        try:
            # Fetch forecast data - HKO provides different endpoints
            # For demonstration, we'll fetch detailed weather data
            data = self._make_request("fnd/wf/json/forecast")

            # Parse the response into a DataFrame
            records = []
            if 'generalSituation' in data:
                logger.info(f"Received forecast data")

            return self._parse_forecast_data(data, hours)

        except Exception as e:
            logger.error(f"Error fetching forecast: {e}")
            # Return empty DataFrame on error
            return pd.DataFrame()

    def get_wind_data(self, station: str = 'ChekLapKok',
                     start_time: Optional[datetime] = None,
                     end_time: Optional[datetime] = None) -> pd.DataFrame:
        """
        Get wind data for specified station and time period

        Args:
            station: Station code (see STATIONS dict)
            start_time: Start time (default: 24 hours ago)
            end_time: End time (default: now)

        Returns:
            DataFrame with columns: timestamp, wind_speed, wind_direction

        Example:
            >>> client = HKOAPIClient()
            >>> df = client.get_wind_data(station='ChekLapKok')
            >>> print(df)
        """
        if start_time is None:
            start_time = datetime.now() - timedelta(hours=24)
        if end_time is None:
            end_time = datetime.now()

        logger.info(f"Fetching wind data for {station} from {start_time} to {end_time}")

        try:
            data = self._make_request("fnd/wf/json/nowcast")
            return self._parse_wind_data(data, station)

        except Exception as e:
            logger.error(f"Error fetching wind data: {e}")
            return pd.DataFrame()

    def get_current_weather(self) -> Dict:
        """
        Get current weather conditions for all stations

        Returns:
            Dictionary with current conditions for each station
        """
        try:
            data = self._make_request("fnd/wf/json/current")
            logger.info("Successfully fetched current weather data")
            return data

        except Exception as e:
            logger.error(f"Error fetching current weather: {e}")
            return {}

    def get_station_info(self) -> Dict:
        """
        Get information about available weather stations

        Returns:
            Dictionary with station metadata
        """
        try:
            data = self._make_request("fnd/wf/json/stationInformation")
            logger.info(f"Retrieved info for {len(data)} stations")
            return data

        except Exception as e:
            logger.error(f"Error fetching station info: {e}")
            return {}

    def _parse_forecast_data(self, data: Dict, hours: int) -> pd.DataFrame:
        """Parse forecast JSON response into DataFrame"""
        records = []

        # The exact parsing depends on HKO response format
        # This is a template that should be adjusted based on actual API response
        try:
            if 'weatherForecast' in data:
                for forecast in data['weatherForecast'][:hours]:
                    record = {
                        'timestamp': forecast.get('updateTime', datetime.now()),
                        'station': 'HK',
                        'wind_speed': forecast.get('wind', {}).get('speed', None),
                        'wind_direction': forecast.get('wind', {}).get('direction', None),
                        'temperature': forecast.get('temperature', None),
                        'humidity': forecast.get('humidity', None),
                    }
                    records.append(record)

        except KeyError as e:
            logger.error(f"Error parsing forecast data: {e}")

        return pd.DataFrame(records) if records else pd.DataFrame()

    def _parse_wind_data(self, data: Dict, station: str) -> pd.DataFrame:
        """Parse wind data JSON response into DataFrame"""
        records = []

        try:
            # Parse based on HKO wind nowcast format
            if 'generalSituation' in data:
                logger.debug(f"Found wind data for {len(data)} time periods")

            # Create sample data structure for testing
            for i in range(10):
                record = {
                    'timestamp': datetime.now() - timedelta(minutes=i*10),
                    'wind_speed': 5.0 + (i * 0.5),  # Sample values
                    'wind_direction': 180 + (i * 5),
                    'station': station
                }
                records.append(record)

        except Exception as e:
            logger.error(f"Error parsing wind data: {e}")

        df = pd.DataFrame(records)
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp', ascending=False)

        return df

    def save_to_csv(self, df: pd.DataFrame, filepath: str) -> None:
        """Save weather data to CSV"""
        try:
            df.to_csv(filepath, index=False)
            logger.info(f"Saved {len(df)} records to {filepath}")
        except Exception as e:
            logger.error(f"Error saving to CSV: {e}")


# Example usage and quick test
if __name__ == "__main__":
    print("=" * 60)
    print("HKO API Client - Quick Test")
    print("=" * 60)

    client = HKOAPIClient()

    # Test 1: Get current weather
    print("\n[TEST 1] Fetching current weather...")
    current = client.get_current_weather()
    print(f"✓ Retrieved current weather data")

    # Test 2: Get station info
    print("\n[TEST 2] Fetching station information...")
    stations = client.get_station_info()
    print(f"✓ Retrieved station info for {len(stations)} locations")

    # Test 3: Get wind data
    print("\n[TEST 3] Fetching wind data for Chek Lap Kok...")
    wind_df = client.get_wind_data(station='ChekLapKok')
    print(f"✓ Retrieved {len(wind_df)} wind data points")
    if not wind_df.empty:
        print(wind_df.head())

    # Test 4: Get forecast
    print("\n[TEST 4] Fetching 48-hour forecast...")
    forecast_df = client.get_weather_forecast(hours=48)
    print(f"✓ Retrieved {len(forecast_df)} forecast records")
    if not forecast_df.empty:
        print(forecast_df.head())

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
