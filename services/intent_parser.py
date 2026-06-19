import re
from typing import Optional, Dict, Any


class Intent:
    """Parsed user intent"""
    def __init__(self, intent_type: str, entity_type: str, entity_name: str, **kwargs):
        self.intent_type = intent_type  # STATUS, AVAILABILITY, SERVICE, IMPACT, TOPOLOGY
        self.entity_type = entity_type  # DISTRICT, MANDAL, LOCATION, DEVICE, IP, SERVICE
        self.entity_name = entity_name
        self.params = kwargs


def parse_intent(query: str) -> Intent:
    """
    Parse user query to extract intent and entity
    
    Examples:
        "Status of Sangareddy District" → STATUS, DISTRICT, SANGAREDDY
        "Availability of Nagalgidda Mandal" → AVAILABILITY, MANDAL, NAGALGIDDA
        "Service status 123456" → SERVICE, SERVICE, 123456
        "Root cause of OLT001" → IMPACT, DEVICE, OLT001
        "Status of 10.10.20.3" → STATUS, IP, 10.10.20.3
    """
    
    query_lower = query.lower().strip()
    
    # ─────────────────────────────────────────────────────────────────────────
    # INTENT DETECTION
    # ─────────────────────────────────────────────────────────────────────────
    
    intent_type = "STATUS"  # default
    
    if "availability" in query_lower:
        intent_type = "AVAILABILITY"
    elif "service status" in query_lower or "service" in query_lower:
        intent_type = "SERVICE"
    elif "root cause" in query_lower or "impact" in query_lower or "cascading" in query_lower:
        intent_type = "IMPACT"
    elif "topology" in query_lower or "path" in query_lower:
        intent_type = "TOPOLOGY"
    
    # ─────────────────────────────────────────────────────────────────────────
    # ENTITY TYPE & NAME EXTRACTION
    # ─────────────────────────────────────────────────────────────────────────
    
    entity_type, entity_name = extract_entity(query)
    
    return Intent(intent_type, entity_type, entity_name)


def extract_entity(query: str) -> tuple[str, str]:
    """
    Extract entity type and name from query
    
    Returns:
        (entity_type, entity_name)
    """
    
    query_lower = query.lower()
    
    # ─────────────────────────────────────────────────────────────────────────
    # IP ADDRESS
    # ─────────────────────────────────────────────────────────────────────────
    
    ip_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
    ip_match = re.search(ip_pattern, query)
    
    if ip_match:
        return ("IP", ip_match.group())
    
    # ─────────────────────────────────────────────────────────────────────────
    # SERVICE ID (numeric)
    # ─────────────────────────────────────────────────────────────────────────
    
    if "service" in query_lower:
        service_match = re.search(r"service\s+(?:id\s+)?(\d+)", query_lower)
        if service_match:
            return ("SERVICE", service_match.group(1))
    
    # ─────────────────────────────────────────────────────────────────────────
    # LGD CODE
    # ─────────────────────────────────────────────────────────────────────────
    
    if "lgd" in query_lower:
        lgd_match = re.search(r"lgd\s+(?:code\s+)?(\d+)", query_lower)
        if lgd_match:
            return ("LGD", lgd_match.group(1))
    
    # ─────────────────────────────────────────────────────────────────────────
    # DEVICE HOSTNAME (e.g., OLT001, ONT-XYZ)
    # ─────────────────────────────────────────────────────────────────────────
    
    device_pattern = r"(?:OLT|ONT|ROUTER|SWITCH|UPS)[\-\d\w]+"
    device_match = re.search(device_pattern, query, re.IGNORECASE)
    
    if device_match:
        return ("DEVICE", device_match.group().upper())
    
    # ─────────────────────────────────────────────────────────────────────────
    # DISTRICT / MANDAL / LOCATION
    # ─────────────────────────────────────────────────────────────────────────
    
    # Extract text after "of" (e.g., "Status of Sangareddy District")
    of_pattern = r"(?:of|in|for)\s+([A-Za-z\s]+?)(?:\s+(?:district|mandal|location|block))?$"
    of_match = re.search(of_pattern, query_lower)
    
    if of_match:
        entity_name = of_match.group(1).strip()
        
        # Determine if district, mandal, or location
        if "district" in query_lower:
            return ("DISTRICT", entity_name)
        elif "mandal" in query_lower or "block" in query_lower:
            return ("MANDAL", entity_name)
        elif "location" in query_lower:
            return ("LOCATION", entity_name)
        else:
            return ("DISTRICT", entity_name)  # default to district
    
    # ─────────────────────────────────────────────────────────────────────────
    # Fallback: extract longest capitalized sequence
    # ─────────────────────────────────────────────────────────────────────────
    
    words = query.split()
    capitalized = [w for w in words if w[0].isupper()]
    
    if capitalized:
        entity_name = " ".join(capitalized)
        
        # Heuristic: if it ends with "District", "Mandal", etc., use that type
        if query_lower.endswith("district"):
            return ("DISTRICT", entity_name)
        elif query_lower.endswith("mandal") or query_lower.endswith("block"):
            return ("MANDAL", entity_name)
        elif query_lower.endswith("location"):
            return ("LOCATION", entity_name)
        else:
            return ("UNKNOWN", entity_name)
    
    return ("UNKNOWN", "")
