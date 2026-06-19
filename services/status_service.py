from services.data_drivers.monitoring_driver import fetch_all_device_status
from services.status_engine import get_status as get_status_from_engine


def fetch_status() -> list[dict]:
    """Legacy cache-refresh entry point."""
    return fetch_all_device_status()


def get_status(query: str) -> dict:
    """Backward-compatible facade for callers that still import status_service."""
    return get_status_from_engine(query)
