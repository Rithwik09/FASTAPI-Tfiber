from services.intent_parser import parse_status_query
from services.resolver_service import resolve_entity
from services.data_drivers.graph_driver import (
    count_affected_services,
    get_devices_for_scope,
)
from services.data_drivers.monitoring_driver import (
    MonitoringAPIError,
    fetch_device_status_batch,
)
from services.data_drivers.aggregator_driver import aggregate_status
from services.data_drivers.compression_driver import compress_status


class StatusEngineError(Exception):
    pass


def get_status(query: str) -> dict:
    try:
        intent = parse_status_query(query)

        if intent.intent_type != "STATUS":
            return {
                "success": False,
                "status": "UNSUPPORTED_INTENT",
                "intent": intent.intent_type,
                "error": f"{intent.intent_type} is not implemented on /status yet",
            }

        if not intent.entity_name:
            return {
                "success": False,
                "status": "UNRESOLVED",
                "error": "No entity found in query",
            }

        resolved = resolve_entity(intent.entity_name, intent.intent_type)

        if resolved.get("status") == "ambiguous":
            return _ambiguous_response(resolved)

        if resolved.get("status") != "resolved":
            return {
                "success": False,
                "status": "UNRESOLVED",
                "intent": _intent_payload(intent),
                "error": resolved.get("error", "Entity could not be resolved"),
            }

        hostnames = get_devices_for_scope(resolved)

        if not hostnames:
            empty = aggregate_status(
                entity_type=resolved.get("entity_type"),
                entity_name=resolved.get("entity_name"),
                scope=resolved.get("scope_level", "UNKNOWN"),
                devices=[],
            )
            return {
                "success": False,
                "status": "NO_DEVICES",
                "intent": _intent_payload(intent),
                "resolver_context": _resolver_context(resolved),
                "data": compress_status(resolved, empty, []),
                "error": "No devices found for resolved entity",
            }

        monitoring_by_hostname = fetch_device_status_batch(hostnames)
        devices = list(monitoring_by_hostname.values())
        affected_services = count_affected_services(devices)

        aggregated = aggregate_status(
            entity_type=resolved.get("entity_type"),
            entity_name=resolved.get("entity_name"),
            scope=resolved.get("scope_level", "UNKNOWN"),
            devices=devices,
            affected_services=affected_services,
        )
        compressed = compress_status(resolved, aggregated, devices)

        return {
            "success": True,
            "status": "OK",
            "intent": _intent_payload(intent),
            "resolver_context": _resolver_context(resolved),
            "raw_device_count": len(devices),
            "data": compressed,
        }

    except MonitoringAPIError as exc:
        return {
            "success": False,
            "status": "MONITORING_ERROR",
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "success": False,
            "status": "ENGINE_ERROR",
            "error": f"Status engine error: {exc}",
        }


def _ambiguous_response(resolved: dict) -> dict:
    return {
        "success": False,
        "status": "AMBIGUOUS",
        "entity_type": resolved.get("entity_type"),
        "entity_name": resolved.get("entity_name"),
        "lookup_type": resolved.get("lookup_type"),
        "candidates": resolved.get("candidates", []),
        "error": resolved.get("error", "Multiple matching entities found"),
    }


def _intent_payload(intent) -> dict:
    return {
        "intent": intent.intent_type,
        "entity_type": intent.entity_type,
        "entity_name": intent.entity_name,
    }


def _resolver_context(resolved: dict) -> dict:
    return {
        "entity_type": resolved.get("entity_type"),
        "entity_name": resolved.get("entity_name"),
        "lookup_type": resolved.get("lookup_type"),
        "scope": resolved.get("scope_level"),
        "confidence": resolved.get("confidence"),
        "canonical_id": resolved.get("canonical_id"),
    }


def get_device_impact(hostname: str) -> dict:
    return {
        "device": hostname,
        "status": "NOT_IMPLEMENTED",
        "message": "Impact analysis will be handled by /impact-analysis",
    }
