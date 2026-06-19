import re

from neo4j.device_queries import (
    get_device_by_ip,
    get_device_by_hostname,
    get_device_by_serial
)

from neo4j.district_queries import (
    get_district
)

IP_PATTERN = r"^\d+\.\d+\.\d+\.\d+$"


def resolve_entity(query: str):

    query = query.strip()

    #
    # IP
    #

    if re.match(IP_PATTERN, query):

        devices = get_device_by_ip(query)

        return {
            "entity_type": "DEVICE",
            "lookup_type": "IP",
            "matches": devices
        }

    #
    # district
    #

    district = get_district(query)

    if district:

        return {
            "entity_type": "DISTRICT",
            "lookup_type": "NAME",
            "district": district
        }

    #
    # hostname
    #

    device = get_device_by_hostname(query)

    if device:

        return {
            "entity_type": "DEVICE",
            "lookup_type": "HOSTNAME",
            "device": device
        }

    #
    # serial
    #

    device = get_device_by_serial(query)

    if device:

        return {
            "entity_type": "DEVICE",
            "lookup_type": "SERIAL",
            "device": device
        }

    return {
        "entity_type": "UNKNOWN"
    }