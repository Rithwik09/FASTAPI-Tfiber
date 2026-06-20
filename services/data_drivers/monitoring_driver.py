"""
Monitoring API driver to fetch device status
"""

import requests
from requests.auth import HTTPBasicAuth
from typing import Optional
import os

from cache.status_cache import status_data
from services.topology_data import topo

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


def get_status_inventory() -> list[dict]:
    """Use the refreshed cache when available; otherwise call the monitoring API."""
    if status_data:
        return list(status_data)

    return fetch_all_device_status()


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
    all_devices = get_status_inventory()
    
    device_lookup = {}
    for device in all_devices:
        for key in ("hostname", "Hostname", "OLT", "networkname"):
            value = str(device.get(key, "")).upper()
            if value:
                device_lookup[value] = device
    
    # Filter to requested hostnames
    result = {}
    for hostname in hostnames:
        hostname_upper = str(hostname).upper()
        if hostname_upper in device_lookup:
            result[hostname_upper] = device_lookup[hostname_upper]
        else:
            result[hostname_upper] = {
                "hostname": hostname_upper,
                "SystemDown": "UNKNOWN",
                "status": "NOT_FOUND"
            }
    
    return result


def fetch_devices_for_resolved_scope(
    resolved: dict,
    hostnames: list[str] | None = None,
) -> tuple[list[dict], str]:
    """
    Combine Neo4j resolution with Status API inventory.

    If Neo4j already returned hostnames, use those as the strongest filter.
    If Neo4j has no device edges yet, fall back to Status API fields.
    """
    if hostnames:
        devices = list(fetch_device_status_batch(hostnames).values())
        if any(device.get("status") != "NOT_FOUND" for device in devices):
            return devices, "NEO4J_HOSTNAMES"

    inventory = get_status_inventory()
    entity_type = resolved.get("entity_type")
    entity_name = resolved.get("entity_name")
    context = resolved.get("context") or {}

    if entity_type == "DISTRICT":
        return [
            device for device in inventory
            if _matches_any(device, ("DISTRICT", "District"), entity_name)
        ], "STATUS_API_DISTRICT"

    if entity_type == "MANDAL":
        return [
            device for device in inventory
            if _matches_any(device, ("BLOCK", "Block", "MANDAL", "Mandal"), entity_name)
        ], "STATUS_API_MANDAL"

    if entity_type == "LOCATION":
        location_names = [
            entity_name,
            context.get("name"),
            context.get("location"),
            context.get("location_name"),
        ]
        location_codes = [
            context.get("code"),
            context.get("location_code"),
            context.get("lgd_code"),
            context.get("LGDCode"),
        ]

        return [
            device for device in inventory
            if _matches_any(device, ("LOCATION", "Location"), *location_names)
            or _matches_any(device, ("LGDCode", "lgd_code", "LGD"), *location_codes)
        ], "STATUS_API_LOCATION"

    if entity_type == "LGD":
        return [
            device for device in inventory
            if _matches_any(device, ("LGDCode", "lgd_code", "LGD"), entity_name)
        ], "STATUS_API_LGD"

    if entity_type == "IP":
        return [
            device for device in inventory
            if _matches_any(device, ("IPAddress", "ip_address", "ip"), entity_name)
        ], "STATUS_API_IP"

    if entity_type == "DEVICE":
        return [
            device for device in inventory
            if _matches_device(device, entity_name, context)
        ], "STATUS_API_DEVICE"

    return [], "STATUS_API_NO_MATCH"


def fetch_device_status(hostname: str) -> Optional[dict]:
    """
    Fetch status for a single device
    """
    all_devices = get_status_inventory()
    
    hostname_upper = hostname.upper()
    
    for device in all_devices:
        if device.get("hostname", "").upper() == hostname_upper:
            return device
    
    return None


def _matches_device(device: dict, entity_name: str, context: dict) -> bool:
    values = [
        entity_name,
        context.get("hostname"),
        context.get("Hostname"),
        context.get("ip_address"),
        context.get("IPAddress"),
        context.get("ip"),
    ]

    return (
        _matches_any(device, ("hostname", "Hostname", "OLT", "networkname"), *values)
        or _matches_any(device, ("IPAddress", "ip_address", "ip"), *values)
    )


def _matches_any(device: dict, fields: tuple[str, ...], *values) -> bool:
    expected = {
        _normalize(value)
        for value in values
        if value is not None and str(value).strip()
    }

    if not expected:
        return False

    return any(
        _normalize(device.get(field)) in expected
        for field in fields
    )


def _normalize(value) -> str:
    return str(value or "").strip().upper()


def classify_device_type(device: dict) -> str:
    """
    Classify device type from monitoring data
    
    Returns: OLT, ONT, Router, Switch, UPS, Other
    """
    topology_type = topo.resolve_device_type(device)
    canonical_type = _canonical_device_type(topology_type)
    if canonical_type:
        return canonical_type

    # With topology loaded, unmatched monitoring records are intentionally Other.
    if topo.is_loaded:
        return "Other"

    hostname = str(
        device.get("hostname")
        or device.get("Hostname")
        or device.get("OLT")
        or ""
    ).upper()
    vendor = str(device.get("VENDOR", "")).upper()
    ems_type = str(device.get("EMS_TYPE", "")).upper()
    
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


def _canonical_device_type(value) -> str | None:
    normalized = str(value or "").strip().upper()
    aliases = {
        "OLT": "OLT",
        "ONT": "ONT",
        "ROUTER": "Router",
        "SWITCH": "Switch",
        "UPS": "UPS",
    }
    return aliases.get(normalized)


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
