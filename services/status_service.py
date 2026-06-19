"""
Status Service with Scope-Based Compression

Handles the complete flow:
1. Parse intent from query
2. Resolve entity (with context)
3. Get devices from Neo4j based on scope
4. Fetch status from monitoring API
5. Aggregate based on scope level
6. Return compressed JSON for LLM
"""

import requests
from requests.auth import HTTPBasicAuth
from collections import Counter
import os

from services.intent_parser import parse_intent
from services.resolver_service import resolve_entity
from services.data_drivers.neo4j_driver import (
    get_devices_by_district,
    get_devices_by_mandal,
    get_devices_by_location,
    get_devices_by_lgd,
    get_services_for_device
)
from services.data_drivers.monitoring_driver import (
    fetch_device_status_batch,
    classify_device_type
)

MONITORING_URL = os.getenv("MONITORING_URL", "http://tfdcosssm1.tfiber.in:14081/status")
MONITORING_USERNAME = os.getenv("MONITORING_USERNAME", "Tfiber")
MONITORING_PASSWORD = os.getenv("MONITORING_PASSWORD", "Tfiber@2024")


def get_status(query: str) -> dict:
    """
    Get comprehensive status with scope-based compression.
    
    Flow:
        Query → Intent Parser → Resolver (enriched) → Neo4j (by scope) 
        → Monitoring → Aggregation (by scope) → Compressed JSON
    """
    
    try:
        print(f"\n[STATUS] Query: {query}")
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 1: PARSE INTENT
        # ─────────────────────────────────────────────────────────────────────
        
        intent = parse_intent(query)
        print(f"[Intent] {intent.intent_type}, {intent.entity_type}: {intent.entity_name}")
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 2: RESOLVE ENTITY (with enriched context)
        # ─────────────────────────────────────────────────────────────────────
        
        resolved = resolve_entity(intent.entity_name, intent.intent_type)
        print(f"[Resolver] Status: {resolved['status']}, Scope: {resolved.get('scope_level')}")
        
        if resolved["status"] == "unresolved":
            return {
                "success": False,
                "error": resolved.get("error", "Entity not resolved")
            }
        
        if resolved["status"] == "ambiguous":
            return {
                "success": False,
                "error": "Ambiguous entity",
                "candidates": resolved.get("candidates"),
                "context": resolved.get("error")
            }
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 3: GET DEVICES BY SCOPE LEVEL
        # ─────────────────────────────────────────────────────────────────────
        
        entity_type = resolved["entity_type"]
        entity_name = resolved["entity_name"]
        scope_level = resolved.get("scope_level", "DEVICE")
        
        hostnames = _get_devices_by_scope(entity_type, entity_name)
        
        if not hostnames:
            return {
                "success": False,
                "error": f"No devices found for {entity_type}: {entity_name}"
            }
        
        print(f"[Neo4j] Found {len(hostnames)} devices")
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 4: FETCH DEVICE STATUS
        # ─────────────────────────────────────────────────────────────────────
        
        device_status = fetch_device_status_batch(hostnames)
        devices = list(device_status.values())
        
        print(f"[Monitoring] Fetched status for {len(devices)} devices")
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 5: AGGREGATE WITH SCOPE-BASED COMPRESSION
        # ─────────────────────────────────────────────────────────────────────
        
        aggregated = _aggregate_by_scope(
            scope_level,
            entity_type,
            entity_name,
            devices
        )
        
        print(f"[Aggregation] Health: {aggregated['overall_health']}, " +
              f"Devices: {aggregated['devices_up']}/{aggregated['total_devices']}")
        
        return {
            "success": True,
            "data": aggregated,
            "scope": scope_level,
            "resolver_context": {
                "lookup_type": resolved["lookup_type"],
                "confidence": resolved["confidence"],
                "canonical_id": resolved.get("canonical_id")
            }
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Status engine error: {str(e)}"
        }


def _get_devices_by_scope(entity_type: str, entity_name: str) -> list[str]:
    """Get device list based on entity type (scope)"""
    
    if entity_type == "DISTRICT":
        return get_devices_by_district(entity_name)
    
    elif entity_type == "MANDAL":
        return get_devices_by_mandal(entity_name)
    
    elif entity_type == "LOCATION":
        return get_devices_by_location(entity_name)
    
    elif entity_type == "DEVICE":
        return [entity_name]
    
    elif entity_type == "IP":
        return [entity_name]
    
    else:
        return []


def _aggregate_by_scope(
    scope_level: str,
    entity_type: str,
    entity_name: str,
    devices: list[dict]
) -> dict:
    """
    Aggregate device data with scope-based compression.
    
    Scope levels determine compression:
    - NETWORK: Only totals (no breakdown)
    - DISTRICT: Totals + mandal breakdown
    - MANDAL: Totals + location breakdown
    - LOCATION: Totals + device breakdown
    - DEVICE: Single device details + immediate parent path
    """
    
    if not devices:
        return {
            "entity_type": entity_type,
            "entity_name": entity_name,
            "scope": scope_level,
            "overall_health": "UNKNOWN",
            "total_devices": 0,
            "devices_up": 0,
            "devices_down": 0,
            "availability": 0.0,
            "critical_alerts": 0,
            "affected_services": 0,
            "device_breakdown": {}
        }
    
    # ─────────────────────────────────────────────────────────────────────────
    # BASIC STATS
    # ─────────────────────────────────────────────────────────────────────────
    
    total = len(devices)
    up = sum(1 for d in devices if d.get("SystemDown") == "UP")
    down = total - up
    availability = round((up / total * 100), 2) if total > 0 else 0.0
    
    # ─────────────────────────────────────────────────────────────────────────
    # DEVICE TYPE BREAKDOWN (always included)
    # ─────────────────────────────────────────────────────────────────────────
    
    device_types = [classify_device_type(d) for d in devices]
    type_counts = Counter(device_types)
    
    device_breakdown = {
        "OLT": type_counts.get("OLT", 0),
        "ONT": type_counts.get("ONT", 0),
        "Router": type_counts.get("Router", 0),
        "Switch": type_counts.get("Switch", 0),
        "UPS": type_counts.get("UPS", 0),
        "Other": type_counts.get("Other", 0)
    }
    
    # ─────────────────────────────────────────────────────────────────────────
    # HEALTH CLASSIFICATION
    # ─────────────────────────────────────────────────────────────────────────
    
    down_percentage = (down / total * 100) if total > 0 else 0
    
    if down_percentage == 0:
        overall_health = "Healthy"
    elif down_percentage < 5:
        overall_health = "Degraded"
    else:
        overall_health = "Critical"
    
    # ─────────────────────────────────────────────────────────────────────────
    # ALERTS & IMPACT (scope-aware)
    # ─────────────────────────────────────────────────────────────────────────
    
    down_devices = [d for d in devices if d.get("SystemDown") == "DOWN"]
    critical_alerts = len(down_devices)
    affected_services = len(set([d.get("service_id") for d in down_devices if d.get("service_id")]))
    
    # ─────────────────────────────────────────────────────────────────────────
    # SCOPE-SPECIFIC COMPRESSION
    # ─────────────────────────────────────────────────────────────────────────
    
    result = {
        "entity_type": entity_type,
        "entity_name": entity_name,
        "scope": scope_level,
        "overall_health": overall_health,
        "total_devices": total,
        "devices_up": up,
        "devices_down": down,
        "availability": availability,
        "critical_alerts": critical_alerts,
        "affected_services": affected_services,
        "device_breakdown": device_breakdown
    }
    
    # NETWORK/DISTRICT/MANDAL: Add top issues only
    if scope_level in ["NETWORK", "DISTRICT", "MANDAL"]:
        top_issues = []
        if down > 0:
            top_issues.append(f"{down} devices DOWN")
        
        vendors_down = Counter([d.get("VENDOR", "UNKNOWN") for d in down_devices])
        if vendors_down:
            top_vendor, count = vendors_down.most_common(1)[0]
            top_issues.append(f"{top_vendor}: {count} affected")
        
        result["top_issues"] = top_issues[:2]
    
    # LOCATION/DEVICE: Add more detailed breakdown
    if scope_level in ["LOCATION", "DEVICE"]:
        if down_devices:
            down_breakdown = Counter([d.get("VENDOR", "UNKNOWN") for d in down_devices])
            result["down_by_vendor"] = dict(down_breakdown.most_common(3))
    
    return result
