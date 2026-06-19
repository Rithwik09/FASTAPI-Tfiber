"""
Extended Entity Resolver
Returns not just entity identity, but full context for status engine.

Output structure:
{
    "status": "resolved" | "ambiguous" | "unresolved",
    "intent": "STATUS" | "AVAILABILITY" | "SERVICE" | "IMPACT" | "TOPOLOGY",
    "entity_type": "DISTRICT" | "MANDAL" | "LOCATION" | "DEVICE" | "IP" | "SERVICE" | "LGD",
    "entity_name": str,
    "canonical_id": str,
    "lookup_type": "NAME" | "IP" | "HOSTNAME" | "SERIAL" | "ID",
    "confidence": 0.0-1.0,
    "scope_level": "NETWORK" | "DISTRICT" | "MANDAL" | "LOCATION" | "DEVICE",
    "requires_monitoring": bool,
    "requires_topology": bool,
    "candidates": list (if ambiguous),
    "context": dict (Neo4j node data)
}
"""

import re
from typing import Optional

from graphdb.device_queries import (
    get_device_by_ip,
    get_device_by_hostname,
    get_device_by_serial
)

from graphdb.district_queries import (
    get_district,
    get_mandal,
    get_location_by_lgd,
    get_location_by_code
)

IP_PATTERN = r"^\d+\.\d+\.\d+\.\d+$"


def resolve_entity(query: str, intent: str = "STATUS") -> dict:
    """
    Resolve entity and return enriched context.
    
    Args:
        query: User input (IP, hostname, district name, etc.)
        intent: User intent (STATUS, AVAILABILITY, SERVICE, IMPACT, TOPOLOGY)
    
    Returns:
        Enriched resolution context with scope, confidence, and metadata
    """
    
    query = query.strip()
    
    # ─────────────────────────────────────────────────────────────────────────
    # IP ADDRESS (highest priority - most specific)
    # ─────────────────────────────────────────────────────────────────────────
    
    if re.match(IP_PATTERN, query):
        devices = get_device_by_ip(query)
        
        if len(devices) == 1:
            return {
                "status": "resolved",
                "intent": intent,
                "entity_type": "DEVICE",
                "entity_name": devices[0].get("hostname", query),
                "canonical_id": devices[0].get("id"),
                "lookup_type": "IP",
                "confidence": 1.0,
                "scope_level": "DEVICE",
                "requires_monitoring": True,
                "requires_topology": True,
                "context": devices[0]
            }
        
        elif len(devices) > 1:
            # Ambiguous: multiple devices with same IP
            return {
                "status": "ambiguous",
                "intent": intent,
                "entity_type": "DEVICE",
                "entity_name": query,
                "lookup_type": "IP",
                "confidence": 0.5,
                "scope_level": "DEVICE",
                "requires_monitoring": True,
                "requires_topology": True,
                "candidates": [
                    {
                        "hostname": d.get("hostname"),
                        "device_type": d.get("device_type"),
                        "location": d.get("location")
                    }
                    for d in devices
                ],
                "error": f"Multiple devices found for IP {query}. Please specify device type."
            }
        else:
            return {
                "status": "unresolved",
                "intent": intent,
                "entity_type": "UNKNOWN",
                "entity_name": query,
                "lookup_type": "IP",
                "confidence": 0.0,
                "error": f"No device found for IP: {query}"
            }
    
    # ─────────────────────────────────────────────────────────────────────────
    # HOSTNAME (e.g., OLT001, ONT-XYZ)
    # ─────────────────────────────────────────────────────────────────────────
    
    device = get_device_by_hostname(query)
    
    if device:
        return {
            "status": "resolved",
            "intent": intent,
            "entity_type": "DEVICE",
            "entity_name": device.get("hostname"),
            "canonical_id": device.get("id"),
            "lookup_type": "HOSTNAME",
            "confidence": 1.0,
            "scope_level": "DEVICE",
            "requires_monitoring": True,
            "requires_topology": True,
            "context": device
        }
    
    # ─────────────────────────────────────────────────────────────────────────
    # SERIAL NUMBER
    # ─────────────────────────────────────────────────────────────────────────
    
    device = get_device_by_serial(query)
    
    if device:
        return {
            "status": "resolved",
            "intent": intent,
            "entity_type": "DEVICE",
            "entity_name": device.get("hostname"),
            "canonical_id": device.get("id"),
            "lookup_type": "SERIAL",
            "confidence": 1.0,
            "scope_level": "DEVICE",
            "requires_monitoring": True,
            "requires_topology": True,
            "context": device
        }
    
    # ─────────────────────────────────────────────────────────────────────────
    # LGD CODE (Location by LGD code - canonical Location mapping)
    # ─────────────────────────────────────────────────────────────────────────
    
    if query.isdigit() and len(query) == 6:
        location = get_location_by_lgd(query)
        
        if location:
            return {
                "status": "resolved",
                "intent": intent,
                "entity_type": "LOCATION",
                "entity_name": location.get("name", query),
                "canonical_id": location.get("id"),
                "lookup_type": "LGD",
                "confidence": 1.0,
                "scope_level": "LOCATION",
                "requires_monitoring": True,
                "requires_topology": True,
                "context": location
            }
    
    # ─────────────────────────────────────────────────────────────────────────
    # DISTRICT
    # ─────────────────────────────────────────────────────────────────────────
    
    district = get_district(query)
    
    if district:
        return {
            "status": "resolved",
            "intent": intent,
            "entity_type": "DISTRICT",
            "entity_name": district.get("name"),
            "canonical_id": district.get("id"),
            "lookup_type": "NAME",
            "confidence": 1.0,
            "scope_level": "DISTRICT",
            "requires_monitoring": True,
            "requires_topology": False,
            "context": district
        }
    
    # ─────────────────────────────────────────────────────────────────────────
    # MANDAL
    # ─────────────────────────────────────────────────────────────────────────
    
    mandal = get_mandal(query)
    
    if mandal:
        return {
            "status": "resolved",
            "intent": intent,
            "entity_type": "MANDAL",
            "entity_name": mandal.get("name"),
            "canonical_id": mandal.get("id"),
            "lookup_type": "NAME",
            "confidence": 1.0,
            "scope_level": "MANDAL",
            "requires_monitoring": True,
            "requires_topology": False,
            "context": mandal
        }
    
    # ─────────────────────────────────────────────────────────────────────────
    # LOCATION BY CODE
    # ─────────────────────────────────────────────────────────────────────────
    
    location = get_location_by_code(query)
    
    if location:
        return {
            "status": "resolved",
            "intent": intent,
            "entity_type": "LOCATION",
            "entity_name": location.get("name", query),
            "canonical_id": location.get("id"),
            "lookup_type": "CODE",
            "confidence": 0.8,
            "scope_level": "LOCATION",
            "requires_monitoring": True,
            "requires_topology": False,
            "context": location
        }
    
    # ─────────────────────────────────────────────────────────────────────────
    # UNRESOLVED
    # ─────────────────────────────────────────────────────────────────────────
    
    return {
        "status": "unresolved",
        "intent": intent,
        "entity_type": "UNKNOWN",
        "entity_name": query,
        "lookup_type": "UNKNOWN",
        "confidence": 0.0,
        "error": f"Could not resolve entity: {query}"
    }

