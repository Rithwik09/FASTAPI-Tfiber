from collections import Counter

from services.data_drivers.monitoring_driver import classify_device_type


# ---------------------------------------------------------------------------
# Location hierarchy rules used by district summaries
#
# Status API mapping:
#   DISTRICT -> district
#   BLOCK    -> mandal
#   GPNAME   -> gram panchayat (the primary location)
#
# These markers are placeholders rather than real hierarchy names, so they
# must not increase the district's mandal or gram-panchayat totals.
# ---------------------------------------------------------------------------
INVALID_LOCATION_VALUES = {
    "",
    "-",
    "NA",
    "N/A",
    "NAN",
    "NONE",
    "NULL",
    "UNKNOWN",
}


def aggregate_status(
    entity_type: str,
    entity_name: str,
    scope: str,
    devices: list[dict],
    affected_services: int = 0,
) -> dict:
    if not devices:
        empty_status = {
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

        # Pointer: keep the district response shape stable even when its
        # inventory is empty; both hierarchy counts correctly become zero.
        if _is_district_scope(entity_type, scope):
            empty_status["location_summary"] = _district_location_summary([])

        return empty_status

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

    status = {
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

    # Pointer: hierarchy totals belong only to a district response. Mandal,
    # location, and device responses retain their existing compact payloads.
    if _is_district_scope(entity_type, scope):
        status["location_summary"] = _district_location_summary(devices)

    return status


def _is_district_scope(entity_type: str, scope: str) -> bool:
    """Return True when either resolver field identifies district scope."""
    return any(
        str(value or "").strip().upper() == "DISTRICT"
        for value in (entity_type, scope)
    )


def _district_location_summary(devices: list[dict]) -> dict[str, int]:
    """Count unique mandals and gram panchayats represented by devices.

    A Status API row represents a device, so the same BLOCK and GPNAME can
    appear many times. Sets turn those repeated device rows into location
    counts. A GP is keyed by (BLOCK, GPNAME), because the same GP name may
    legitimately occur below two different mandals.
    """
    mandals: set[str] = set()
    gram_panchayats: set[tuple[str, str]] = set()

    for device in devices:
        mandal = _first_location_value(
            device,
            ("BLOCK", "Block", "MANDAL", "Mandal"),
        )
        gp_name = _first_location_value(
            device,
            ("GPNAME", "GPName", "gp_name"),
        )

        if mandal:
            mandals.add(mandal)

        if gp_name:
            # Pointer: an empty mandal is retained as a neutral parent so a
            # valid GPNAME is still counted when a source row lacks BLOCK.
            gram_panchayats.add((mandal or "", gp_name))

    return {
        "total_mandals": len(mandals),
        "total_gram_panchayats": len(gram_panchayats),
    }


def _first_location_value(device: dict, fields: tuple[str, ...]) -> str | None:
    """Read the first usable hierarchy value and normalize it for counting."""
    for field in fields:
        normalized = _normalize_location_value(device.get(field))
        if normalized:
            return normalized
    return None


def _normalize_location_value(value) -> str | None:
    """Collapse whitespace/case differences and reject placeholder values."""
    normalized = " ".join(str(value or "").split()).upper()
    return None if normalized in INVALID_LOCATION_VALUES else normalized


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
