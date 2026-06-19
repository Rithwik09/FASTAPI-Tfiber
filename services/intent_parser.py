import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Intent:
    intent_type: str
    entity_type: str
    entity_name: str
    params: dict[str, Any] = field(default_factory=dict)


INTENT_KEYWORDS = {
    "AVAILABILITY": ("availability", "uptime"),
    "SERVICE": ("service status", "service"),
    "IMPACT": ("impact", "root cause", "rca", "cascading"),
    "TOPOLOGY": ("topology", "path", "trace"),
}

SCOPE_WORDS = {
    "district": "DISTRICT",
    "mandal": "MANDAL",
    "block": "MANDAL",
    "location": "LOCATION",
    "village": "LOCATION",
}

DEVICE_PREFIXES = (
    "OLT",
    "ONT",
    "RTR",
    "ROUTER",
    "SW",
    "SWITCH",
    "UPS",
    "GI",
)


def parse_status_query(query: str) -> Intent:
    """Parse the user question without resolving the entity."""
    normalized = " ".join((query or "").strip().split())
    intent_type = _detect_intent(normalized)
    entity_type, entity_name = extract_entity(normalized, intent_type)

    return Intent(
        intent_type=intent_type,
        entity_type=entity_type,
        entity_name=entity_name,
    )


def parse_intent(query: str) -> Intent:
    """Backward-compatible name used by older code."""
    return parse_status_query(query)


def extract_entity(query: str, intent_type: str = "STATUS") -> tuple[str, str]:
    if not query:
        return "UNKNOWN", ""

    ip_match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", query)
    if ip_match:
        return "IP", ip_match.group(0)

    service_match = re.search(
        r"\bservice(?:\s+status)?(?:\s+id)?\s+([A-Za-z0-9_-]+)\b",
        query,
        re.IGNORECASE,
    )
    if intent_type == "SERVICE" and service_match:
        return "SERVICE", service_match.group(1).upper()

    lgd_match = re.search(r"\blgd(?:\s+code)?\s+(\d+)\b", query, re.IGNORECASE)
    if lgd_match:
        return "LGD", lgd_match.group(1)

    device_match = _match_device_name(query)
    if device_match:
        return "DEVICE", device_match.upper()

    scoped_entity = _extract_scoped_entity(query)
    if scoped_entity:
        return scoped_entity

    candidate = _strip_question_words(query)
    if candidate:
        return "UNKNOWN", candidate.upper()

    return "UNKNOWN", ""


def _detect_intent(query: str) -> str:
    query_lower = query.lower()

    for intent_type, keywords in INTENT_KEYWORDS.items():
        if any(keyword in query_lower for keyword in keywords):
            return intent_type

    return "STATUS"


def _match_device_name(query: str) -> str | None:
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_-]*\d[A-Za-z0-9_-]*\b", query):
        upper = token.upper()
        if upper.startswith(DEVICE_PREFIXES):
            return upper

    return None


def _extract_scoped_entity(query: str) -> tuple[str, str] | None:
    query_lower = query.lower()
    scope_type = None

    for scope_word, entity_type in SCOPE_WORDS.items():
        if re.search(rf"\b{scope_word}\b", query_lower):
            scope_type = entity_type
            break

    cleaned = _strip_question_words(query)

    if scope_type:
        cleaned = re.sub(
            r"\b(district|mandal|block|location|village)\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
        return scope_type, cleaned.upper()

    if cleaned:
        return "DISTRICT", cleaned.upper()

    return None


def _strip_question_words(query: str) -> str:
    cleaned = re.sub(
        r"\b(status|availability|uptime|of|in|for|the|please|show|give|get|what|is)\b",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    cleaned = " ".join(cleaned.split())
    return cleaned.strip(" ?")
