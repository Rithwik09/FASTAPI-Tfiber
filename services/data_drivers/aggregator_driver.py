from collections import Counter

from services.data_drivers.monitoring_driver import classify_device_type


def aggregate_status(
    entity_type: str,
    entity_name: str,
    scope: str,
    devices: list[dict],
    affected_services: int = 0,
) -> dict:
    if not devices:
        return {
            "entity_type": entity_type,
            "entity_name": entity_name,
            "scope": scope,
            "overall_health": "UNKNOWN",
            "total_devices": 0,
            "devices_up": 0,
            "devices_down": 0,
            "availability": 0.0,
            "critical_alerts": 0,
            "affected_services": 0,
            "device_breakdown": _empty_device_breakdown(),
            "top_issues": ["No devices found"],
            "recommended_actions": ["Verify inventory mapping in Neo4j"],
        }

    total = len(devices)
    up = sum(1 for device in devices if _system_state(device) == "UP")
    down = sum(1 for device in devices if _system_state(device) == "DOWN")
    unknown = total - up - down
    availability = round((up / total) * 100, 2) if total else 0.0

    down_devices = [
        device
        for device in devices
        if _system_state(device) == "DOWN"
    ]
    critical_alerts = _count_critical_alerts(down_devices)
    device_breakdown = _device_breakdown(devices)
    overall_health = _overall_health(total, down, unknown)

    return {
        "entity_type": entity_type,
        "entity_name": entity_name,
        "scope": scope,
        "overall_health": overall_health,
        "total_devices": total,
        "devices_up": up,
        "devices_down": down,
        "availability": availability,
        "critical_alerts": critical_alerts,
        "affected_services": affected_services,
        "device_breakdown": device_breakdown,
        "top_issues": _top_issues(down_devices, down, unknown, total),
        "recommended_actions": _recommended_actions(
            scope=scope,
            availability=availability,
            down=down,
            critical_alerts=critical_alerts,
        ),
    }


def _system_state(device: dict) -> str:
    return str(device.get("SystemDown", "UNKNOWN")).upper()


def _device_breakdown(devices: list[dict]) -> dict:
    counts = Counter(classify_device_type(device) for device in devices)
    breakdown = _empty_device_breakdown()
    breakdown.update({
        device_type: counts.get(device_type, 0)
        for device_type in breakdown
    })
    return breakdown


def _empty_device_breakdown() -> dict:
    return {
        "OLT": 0,
        "ONT": 0,
        "Router": 0,
        "Switch": 0,
        "UPS": 0,
        "Other": 0,
    }


def _count_critical_alerts(down_devices: list[dict]) -> int:
    explicit_critical = [
        device
        for device in down_devices
        if str(device.get("severity", "")).lower() == "critical"
    ]

    return len(explicit_critical) if explicit_critical else len(down_devices)


def _overall_health(total: int, down: int, unknown: int) -> str:
    if not total:
        return "UNKNOWN"

    down_percent = (down / total) * 100

    if down == 0 and unknown == 0:
        return "Healthy"

    if down_percent < 5:
        return "Degraded"

    return "Critical"


def _top_issues(
    down_devices: list[dict],
    down: int,
    unknown: int,
    total: int,
) -> list[str]:
    issues = []

    if down:
        issues.append(f"{down} devices DOWN")

    if unknown:
        issues.append(f"{unknown} devices UNKNOWN")

    vendor_counts = Counter(
        str(device.get("VENDOR") or "UNKNOWN")
        for device in down_devices
    )
    if vendor_counts:
        vendor, count = vendor_counts.most_common(1)[0]
        issues.append(f"{vendor}: {count} affected")

    if not issues and total:
        issues.append("No active device-down issue detected")

    return issues[:3]


def _recommended_actions(
    scope: str,
    availability: float,
    down: int,
    critical_alerts: int,
) -> list[str]:
    actions = []

    if down:
        if scope in {"DISTRICT", "MANDAL", "LOCATION"}:
            actions.append("Investigate affected OLTs and upstream devices")
        else:
            actions.append("Check device reachability and last update time")

    if critical_alerts:
        actions.append(f"Escalate {critical_alerts} critical alert(s) to NOC")

    if availability < 99:
        actions.append("Check upstream routers and transport links")

    if not actions:
        actions.append("Continue monitoring")

    return actions[:3]


def compress_for_llm(status: dict) -> dict:
    """Backward-compatible helper used by older imports."""
    return status
