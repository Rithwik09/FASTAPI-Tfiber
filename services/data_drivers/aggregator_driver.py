"""
Data aggregation and compression layer
Converts raw device data into compressed summary for LLM
"""

from collections import Counter
from models.status_models import DeviceBreakdown, AggregatedStatus
from .monitoring_driver import classify_device_type


def aggregate_status(
    entity_type: str,
    entity_name: str,
    devices: list[dict]
) -> AggregatedStatus:
    """
    Aggregate device-level data into summarized status
    
    Input: List of raw device dicts from monitoring API
    Output: Compressed AggregatedStatus for LLM
    """
    
    if not devices:
        return AggregatedStatus(
            entity_type=entity_type,
            entity_name=entity_name,
            overall_health="UNKNOWN",
            total_devices=0,
            devices_up=0,
            devices_down=0,
            availability=0.0,
            critical_alerts=0,
            affected_services=0,
            device_breakdown=DeviceBreakdown()
        )
    
    # ─────────────────────────────────────────────────────────────────────────
    # COMPUTE BASIC STATS
    # ─────────────────────────────────────────────────────────────────────────
    
    total = len(devices)
    up = sum(1 for d in devices if d.get("SystemDown") == "UP")
    down = total - up
    availability = round((up / total * 100), 2) if total > 0 else 0.0
    
    # ─────────────────────────────────────────────────────────────────────────
    # CLASSIFY DEVICES BY TYPE
    # ─────────────────────────────────────────────────────────────────────────
    
    device_types = [classify_device_type(d) for d in devices]
    type_counts = Counter(device_types)
    
    device_breakdown = DeviceBreakdown(
        OLT=type_counts.get("OLT", 0),
        ONT=type_counts.get("ONT", 0),
        Router=type_counts.get("Router", 0),
        Switch=type_counts.get("Switch", 0),
        UPS=type_counts.get("UPS", 0),
        Other=type_counts.get("Other", 0)
    )
    
    # ─────────────────────────────────────────────────────────────────────────
    # DETERMINE OVERALL HEALTH
    # ─────────────────────────────────────────────────────────────────────────
    
    down_percentage = (down / total * 100) if total > 0 else 0
    
    if down_percentage == 0:
        overall_health = "Healthy"
    elif down_percentage < 5:
        overall_health = "Degraded"
    elif down_percentage < 20:
        overall_health = "Critical"
    else:
        overall_health = "Critical"
    
    # ─────────────────────────────────────────────────────────────────────────
    # COUNT CRITICAL ALERTS (DOWN DEVICES WITH CRITICAL SEVERITY)
    # ─────────────────────────────────────────────────────────────────────────
    
    down_devices = [d for d in devices if d.get("SystemDown") == "DOWN"]
    critical_alerts = len([
        d for d in down_devices
        if d.get("severity", "").lower() == "critical"
    ]) if down_devices else len(down_devices)
    
    # ─────────────────────────────────────────────────────────────────────────
    # ESTIMATE AFFECTED SERVICES (stub for now)
    # ─────────────────────────────────────────────────────────────────────────
    
    affected_services = len(set([
        d.get("service_id")
        for d in down_devices
        if d.get("service_id")
    ]))
    
    # ─────────────────────────────────────────────────────────────────────────
    # TOP ISSUES
    # ─────────────────────────────────────────────────────────────────────────
    
    top_issues = []
    if down > 0:
        top_issues.append(f"{down} devices DOWN ({down_percentage:.1f}%)")
    
    vendors_down = Counter([d.get("VENDOR", "UNKNOWN") for d in down_devices])
    if vendors_down:
        top_vendor, top_vendor_count = vendors_down.most_common(1)[0]
        top_issues.append(f"{top_vendor}: {top_vendor_count} devices affected")
    
    # ─────────────────────────────────────────────────────────────────────────
    # RECOMMENDED ACTIONS
    # ─────────────────────────────────────────────────────────────────────────
    
    recommended_actions = []
    
    if down > 0:
        recommended_actions.append(
            f"Investigate {down} DOWN device(s)"
        )
    
    if availability < 99.0:
        recommended_actions.append(
            f"Check critical infrastructure (Availability: {availability}%)"
        )
    
    if critical_alerts > 0:
        recommended_actions.append(
            f"Escalate {critical_alerts} critical alert(s) to NOC"
        )
    
    # ─────────────────────────────────────────────────────────────────────────
    # RETURN AGGREGATED STATUS
    # ─────────────────────────────────────────────────────────────────────────
    
    return AggregatedStatus(
        entity_type=entity_type,
        entity_name=entity_name,
        overall_health=overall_health,
        total_devices=total,
        devices_up=up,
        devices_down=down,
        availability=availability,
        critical_alerts=critical_alerts,
        affected_services=affected_services,
        device_breakdown=device_breakdown,
        top_issues=top_issues[:3],  # Top 3 issues
        recommended_actions=recommended_actions[:3]  # Top 3 actions
    )


def compress_for_llm(status: AggregatedStatus) -> dict:
    """
    Convert AggregatedStatus to clean JSON for LLM
    """
    return {
        "entity": {
            "type": status.entity_type,
            "name": status.entity_name
        },
        "health": status.overall_health,
        "devices": {
            "total": status.total_devices,
            "up": status.devices_up,
            "down": status.devices_down,
            "availability_percent": status.availability
        },
        "alerts": {
            "critical": status.critical_alerts,
            "affected_services": status.affected_services
        },
        "breakdown": status.device_breakdown.model_dump(),
        "top_issues": status.top_issues,
        "recommended_actions": status.recommended_actions
    }
