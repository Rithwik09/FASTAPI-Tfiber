from cache.status_cache import status_data


def filter_devices(
    district=None,
    system_down=None,
    vendor=None,
    olt=None,
    ip_address=None,
    lgd_code=None
):

    results = status_data

    if district:

        results = [
            d for d in results
            if d.get(
                "DISTRICT",
                ""
            ).upper() == district.upper()
        ]

    if system_down:

        results = [
            d for d in results
            if d.get(
                "SystemDown",
                ""
            ).upper() == system_down.upper()
        ]

    if vendor:

        results = [
            d for d in results
            if d.get(
                "VENDOR",
                ""
            ).upper() == vendor.upper()
        ]

    if olt:

        results = [
            d for d in results
            if d.get(
                "OLT",
                ""
            ).upper() == olt.upper()
        ]

    if ip_address:

        results = [
        d for d in results
        if d.get(
            "IPAddress",
            ""
        ) == ip_address
    ]

    if lgd_code:

        results = [
        d for d in results
        if str(
            d.get(
                "LGDCode",
                ""
            )
        ) == str(lgd_code)
    ]
        
    

    return results