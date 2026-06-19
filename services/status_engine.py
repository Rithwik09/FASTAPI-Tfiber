"""
Status Engine - Main orchestrator
Coordinates: Intent → Resolver → Neo4j → Monitoring → Aggregation → LLM Response
"""

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
    MonitoringAPIError
)
from services.data_drivers.aggregator_driver import (
    aggregate_status,
    compress_for_llm
)
from models.status_models import StatusResponse, AggregatedStatus


class StatusEngineError(Exception):
    """Status engine error"""
    pass


def get_status(query: str) -> StatusResponse:
    """
    Main entry point: Get comprehensive status for any entity
    
    Flow:
        1. Parse intent from query
        2. Resolve entity (validate existence)
        3. Query Neo4j to get devices
        4. Fetch device status from monitoring API
        5. Aggregate and compress data
        6. Return clean JSON for LLM
    """
    
    try:
        # ─────────────────────────────────────────────────────────────────────
        # STEP 1: PARSE INTENT
        # ─────────────────────────────────────────────────────────────────────
        
        intent = parse_intent(query)
        print(f"[Intent] Type: {intent.intent_type}, Entity: {intent.entity_type} ({intent.entity_name})")
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 2: RESOLVE ENTITY (validate it exists)
        # ─────────────────────────────────────────────────────────────────────
        
        resolved = resolve_entity(intent.entity_name)
        
        if resolved.get("entity_type") == "UNKNOWN":
            return StatusResponse(
                success=False,
                error=f"Could not resolve entity: {intent.entity_name}"
            )
        
        print(f"[Resolver] Entity resolved: {resolved}")
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 3: QUERY NEO4J FOR DEVICES
        # ─────────────────────────────────────────────────────────────────────
        
        hostnames = _get_devices_for_entity(intent.entity_type, intent.entity_name)
        
        if not hostnames:
            return StatusResponse(
                success=False,
                error=f"No devices found for {intent.entity_type}: {intent.entity_name}",
                data=AggregatedStatus(
                    entity_type=intent.entity_type,
                    entity_name=intent.entity_name,
                    overall_health="UNKNOWN",
                    total_devices=0,
                    devices_up=0,
                    devices_down=0,
                    availability=0.0,
                    critical_alerts=0,
                    affected_services=0
                )
            )
        
        print(f"[Neo4j] Found {len(hostnames)} devices")
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 4: FETCH DEVICE STATUS FROM MONITORING API
        # ─────────────────────────────────────────────────────────────────────
        
        device_status = fetch_device_status_batch(hostnames)
        devices = list(device_status.values())
        
        print(f"[Monitoring] Fetched status for {len(devices)} devices")
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 5: AGGREGATE AND COMPRESS
        # ─────────────────────────────────────────────────────────────────────
        
        aggregated = aggregate_status(
            intent.entity_type,
            intent.entity_name,
            devices
        )
        
        print(f"[Aggregation] Health: {aggregated.overall_health}, " +
              f"Up: {aggregated.devices_up}/{aggregated.total_devices}")
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 6: RETURN CLEAN JSON
        # ─────────────────────────────────────────────────────────────────────
        
        return StatusResponse(
            success=True,
            data=aggregated,
            raw_device_count=len(devices)
        )
    
    except MonitoringAPIError as e:
        return StatusResponse(
            success=False,
            error=f"Monitoring API error: {str(e)}"
        )
    
    except Exception as e:
        return StatusResponse(
            success=False,
            error=f"Status engine error: {str(e)}"
        )


def _get_devices_for_entity(entity_type: str, entity_name: str) -> list[str]:
    """
    Get device list based on entity type
    """
    
    if entity_type == "DISTRICT":
        return get_devices_by_district(entity_name)
    
    elif entity_type == "MANDAL":
        return get_devices_by_mandal(entity_name)
    
    elif entity_type == "LOCATION":
        return get_devices_by_location(entity_name)
    
    elif entity_type == "LGD":
        return get_devices_by_lgd(entity_name)
    
    elif entity_type == "DEVICE":
        return [entity_name]
    
    elif entity_type == "IP":
        # For IP address, resolve to device first
        resolved = resolve_entity(entity_name)
        if resolved.get("matches"):
            return [d.get("hostname") for d in resolved["matches"]]
        return []
    
    else:
        raise StatusEngineError(f"Unknown entity type: {entity_type}")


def get_device_impact(hostname: str) -> dict:
    """
    Get cascading impact of a device failure
    
    Returns:
        {
            "device": {...},
            "affected_services": [...],
            "affected_users": N
        }
    """
    
    services = get_services_for_device(hostname)
    
    return {
        "device": hostname,
        "affected_services": services,
        "affected_users": len(services) * 100  # Placeholder
    }
