DEVICE_SCOPE_FIELDS = (
    "hostname",
    "Hostname",
    "DisplayName",
    "LOGICAL_NAME",
    "networkname",
    "SystemDown",
    "Status",
    "IPAddress",
    "ip_address",
    "SerialNumber",
    "ConfigurationItemType",
    "ConfigurationItemSubType",
    "LOCATION",
    "DISTRICT",
    "BLOCK",
    "VENDOR",
    "EMS_TYPE",
    "lastupdate",
)


def compress_status(
    resolved: dict,
    aggregated: dict,
    devices: list[dict],
) -> dict:
    scope = resolved.get("scope_level") or aggregated.get("scope")

    if scope == "DEVICE":
        return _compress_device_scope(resolved, aggregated, devices)

    return _compress_summary_scope(resolved, aggregated)


def _compress_summary_scope(resolved: dict, aggregated: dict) -> dict:
    # Pointer: this allow-list keeps broad-scope responses compact. District
    # hierarchy counts are already aggregated, so exposing location_summary
    # adds useful context without returning individual inventory records.
    allowed = {
        "entity_type",
        "entity_name",
        "scope",
        "location_summary",
        "overall_health",
        "total_devices",
        "devices_up",
        "devices_down",
        "availability",
        "critical_alerts",
        "affected_services",
        "device_breakdown",
        "top_issues",
        "recommended_actions",
    }

    compressed = {
        key: value
        for key, value in aggregated.items()
        if key in allowed
    }
    compressed["lookup_type"] = resolved.get("lookup_type")
    return compressed


def _compress_device_scope(
    resolved: dict,
    aggregated: dict,
    devices: list[dict],
) -> dict:
    device = devices[0] if devices else {}
    context = resolved.get("context") or {}

    compressed_device = {
        key: device.get(key)
        for key in DEVICE_SCOPE_FIELDS
        if key in device
    }

    hostname = (
        compressed_device.get("hostname")
        or compressed_device.get("Hostname")
        or compressed_device.get("DisplayName")
        or compressed_device.get("LOGICAL_NAME")
        or compressed_device.get("networkname")
        or resolved.get("entity_name")
    )

    return {
        "entity_type": "DEVICE",
        "entity_name": hostname,
        "scope": "DEVICE",
        "hostname": hostname,
        "status": device.get("SystemDown", "UNKNOWN"),
        "location": (
            device.get("LOCATION")
            or context.get("location")
            or context.get("location_name")
        ),
        "district": device.get("DISTRICT") or context.get("district"),
        "overall_health": aggregated.get("overall_health"),
        "total_devices": aggregated.get("total_devices"),
        "devices_up": aggregated.get("devices_up"),
        "devices_down": aggregated.get("devices_down"),
        "availability": aggregated.get("availability"),
        "critical_alerts": aggregated.get("critical_alerts"),
        "affected_services": aggregated.get("affected_services"),
        "device": compressed_device,
        "top_issues": aggregated.get("top_issues", []),
        "recommended_actions": aggregated.get("recommended_actions", []),
    }
