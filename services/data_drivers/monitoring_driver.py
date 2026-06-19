"""
Monitoring API driver to fetch device status
"""

import requests
from requests.auth import HTTPBasicAuth
from typing import Optional
import os

MONITORING_URL = os.getenv("MONITORING_URL", "http://tfdcosssm1.tfiber.in:14081/status")
MONITORING_USERNAME = os.getenv("MONITORING_USERNAME", "Tfiber")
MONITORING_PASSWORD = os.getenv("MONITORING_PASSWORD", "Tfiber@2024")


class MonitoringAPIError(Exception):
    """Custom exception for monitoring API errors"""
    pass


def fetch_all_device_status() -> list[dict]:
    """
    Fetch status for all devices from monitoring API
    
    Returns:
        [
            {
                "hostname": "OLT001",
                "ip": "10.10.20.1",
                "SystemDown": "UP",
                "lastupdate": "2024-01-19 13:30:45",
                ...
            },
            ...
        ]
    """
    try:
        response = requests.get(
            MONITORING_URL,
            auth=HTTPBasicAuth(MONITORING_USERNAME, MONITORING_PASSWORD),
            timeout=120
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise MonitoringAPIError(f"Failed to fetch monitoring data: {str(e)}")


def fetch_device_status_batch(hostnames: list[str]) -> dict[str, dict]:
    """
    Fetch status for a batch of devices
    
    Returns:
        {
            "OLT001": {"hostname": "OLT001", "SystemDown": "UP", ...},
            "OLT002": {"hostname": "OLT002", "SystemDown": "DOWN", ...},
            ...
        }
    """
    all_devices = fetch_all_device_status()
    
    # Create lookup dictionary
    device_lookup = {
        d.get("hostname", "").upper(): d
        for d in all_devices
    }
    
    # Filter to requested hostnames
    result = {}
    for hostname in hostnames:
        if hostname.upper() in device_lookup:
            result[hostname.upper()] = device_lookup[hostname.upper()]
        else:
            result[hostname.upper()] = {
                "hostname": hostname.upper(),
                "SystemDown": "UNKNOWN",
                "status": "NOT_FOUND"
            }
    
    return result


def fetch_device_status(hostname: str) -> Optional[dict]:
    """
    Fetch status for a single device
    """
    all_devices = fetch_all_device_status()
    
    hostname_upper = hostname.upper()
    
    for device in all_devices:
        if device.get("hostname", "").upper() == hostname_upper:
            return device
    
    return None


def classify_device_type(device: dict) -> str:
    """
    Classify device type from monitoring data
    
    Returns: OLT, ONT, Router, Switch, UPS, Other
    """
    hostname = device.get("hostname", "").upper()
    vendor = device.get("VENDOR", "").upper()
    ems_type = device.get("EMS_TYPE", "").upper()
    
    if "OLT" in hostname or "OLT" in vendor or "OLT" in ems_type:
        return "OLT"
    elif "ONT" in hostname or "ONT" in vendor or "ONT" in ems_type:
        return "ONT"
    elif "ROUTER" in hostname or "ROUTER" in vendor:
        return "Router"
    elif "SWITCH" in hostname or "SWITCH" in vendor:
        return "Switch"
    elif "UPS" in hostname or "UPS" in vendor:
        return "UPS"
    else:
        return "Other"


def get_device_status_string(device: dict) -> str:
    """
    Get human-readable status string
    """
    system_down = device.get("SystemDown", "UNKNOWN")
    
    if system_down == "UP":
        return "UP"
    elif system_down == "DOWN":
        return "DOWN"
    else:
        return "UNKNOWN"
