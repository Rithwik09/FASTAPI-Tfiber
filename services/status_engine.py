from services.intent_parser import parse_status_query
from services.resolver_service import resolve_entity
from services.data_drivers.graph_driver import (
    count_affected_services,
    get_devices_for_scope,
)
from services.data_drivers.monitoring_driver import (
    MonitoringAPIError,
    fetch_devices_for_resolved_scope,
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

        resolved, resolver_error = _resolve_or_fallback(intent)

        if resolved.get("status") == "ambiguous":
            return _ambiguous_response(resolved)

        if resolved.get("status") != "resolved":
            return {
                "success": False,
                "status": "UNRESOLVED",
                "intent": _intent_payload(intent),
                "error": resolved.get("error", "Entity could not be resolved"),
            }

        graph_hostnames = []
        graph_warning = None
        if not resolver_error:
            try:
                graph_hostnames = get_devices_for_scope(resolved)
            except Exception as exc:
                graph_warning = f"Neo4j graph lookup unavailable: {exc}"

        devices, inventory_source = fetch_devices_for_resolved_scope(
            resolved,
            graph_hostnames,
        )

        monitoring_ambiguity = _monitoring_ambiguity_response(
            intent=intent,
            resolved=resolved,
            devices=devices,
            inventory_source=inventory_source,
            resolver_warning=resolver_error,
        )
        if monitoring_ambiguity:
            return monitoring_ambiguity

        if not devices:
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
                "resolver_warning": resolver_error,
                "graph_warning": graph_warning,
                "inventory_source": inventory_source,
                "data": compress_status(resolved, empty, []),
                "error": "No devices found in Neo4j relationships or Status API inventory",
            }

        affected_services = 0
        try:
            affected_services = count_affected_services(devices)
        except Exception as exc:
            graph_warning = graph_warning or f"Neo4j service lookup unavailable: {exc}"

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
            "resolver_warning": resolver_error,
            "graph_warning": graph_warning,
            "inventory_source": inventory_source,
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


def _resolve_or_fallback(intent) -> tuple[dict, str | None]:
    try:
        resolved = resolve_entity(intent.entity_name, intent.intent_type)
        if resolved.get("status") != "unresolved":
            return resolved, None

        return _status_api_fallback(intent), (
            f"Neo4j did not resolve {intent.entity_name}; using Status API inventory"
        )
    except Exception as exc:
        return _status_api_fallback(intent), f"Neo4j resolver unavailable: {exc}"


def _status_api_fallback(intent) -> dict:
    return {
        "status": "resolved",
        "intent": intent.intent_type,
        "entity_type": intent.entity_type,
        "entity_name": intent.entity_name,
        "lookup_type": "STATUS_API_FALLBACK",
        "confidence": 0.5,
        "scope_level": _scope_for_entity_type(intent.entity_type),
        "requires_monitoring": True,
        "requires_topology": False,
        "context": {},
    }


def _monitoring_ambiguity_response(
    intent,
    resolved: dict,
    devices: list[dict],
    inventory_source: str,
    resolver_warning: str | None,
) -> dict | None:
    if intent.entity_type != "IP" or len(devices) < 2:
        return None

    candidates = []
    seen = set()
    for device in devices:
        candidate = _monitoring_candidate(device)
        identity = (
            candidate.get("serial_number"),
            candidate.get("hostname"),
            candidate.get("location"),
        )
        if identity in seen:
            continue
        seen.add(identity)
        candidates.append(candidate)

    if len(candidates) < 2:
        return None

    return {
        "success": False,
        "status": "AMBIGUOUS",
        "intent": _intent_payload(intent),
        "resolver_context": _resolver_context(resolved),
        "resolver_warning": resolver_warning,
        "inventory_source": inventory_source,
        "candidates": candidates,
        "error": (
            f"Multiple devices found for IP {intent.entity_name}. "
            "Specify a hostname, serial number, or LGD code."
        ),
    }


def _monitoring_candidate(device: dict) -> dict:
    return {
        "hostname": (
            device.get("hostname")
            or device.get("Hostname")
            or device.get("DisplayName")
            or device.get("LOGICAL_NAME")
            or device.get("networkname")
        ),
        "device_type": (
            device.get("ConfigurationItemType")
            or device.get("ConfigurationItemSubType")
            or device.get("device_type")
        ),
        "serial_number": (
            device.get("SerialNumber")
            or device.get("serial_number")
            or device.get("serial")
        ),
        "ip_address": (
            device.get("IPAddress")
            or device.get("ip_address")
            or device.get("ip")
        ),
        "district": device.get("DISTRICT") or device.get("District"),
        "mandal": (
            device.get("BLOCK")
            or device.get("Block")
            or device.get("MANDAL")
            or device.get("Mandal")
        ),
        "location": device.get("LOCATION") or device.get("Location"),
        "status": device.get("SystemDown", "UNKNOWN"),
    }


def _scope_for_entity_type(entity_type: str) -> str:
    if entity_type in {"DISTRICT", "MANDAL", "LOCATION", "DEVICE"}:
        return entity_type

    if entity_type in {"IP", "LGD"}:
        return "DEVICE" if entity_type == "IP" else "LOCATION"

    return "UNKNOWN"


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
