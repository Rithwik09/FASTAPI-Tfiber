from services.data_drivers.neo4j_driver import (
    get_devices_by_district,
    get_devices_by_mandal,
    get_devices_by_location,
    get_devices_by_lgd,
    get_services_for_device,
)


def get_devices_for_scope(resolved: dict) -> list[str]:
    entity_type = resolved.get("entity_type")
    entity_name = resolved.get("entity_name")
    context = resolved.get("context") or {}

    if entity_type == "DISTRICT":
        return get_devices_by_district(entity_name)

    if entity_type == "MANDAL":
        return get_devices_by_mandal(entity_name)

    if entity_type == "LOCATION":
        lgd_code = context.get("lgd_code") or context.get("LGDCode")
        if lgd_code:
            return get_devices_by_lgd(str(lgd_code))

        location_code = context.get("code") or context.get("location_code")
        return get_devices_by_location(location_code or entity_name)

    if entity_type == "LGD":
        return get_devices_by_lgd(entity_name)

    if entity_type == "DEVICE":
        return [entity_name]

    return []


def count_affected_services(devices: list[dict]) -> int:
    down_hostnames = {
        _device_hostname(device)
        for device in devices
        if str(device.get("SystemDown", "")).upper() == "DOWN"
    }
    down_hostnames.discard("")

    services = set()
    for hostname in down_hostnames:
        services.update(get_services_for_device(hostname))

    return len(services)


def _device_hostname(device: dict) -> str:
    return str(
        device.get("hostname")
        or device.get("Hostname")
        or device.get("OLT")
        or ""
    ).upper()
