from neo4j.connection import driver


def get_device_by_hostname(hostname: str):

    with driver.session() as session:

        result = session.run(
            """
            MATCH (d:Device)
            WHERE toLower(d.hostname)=toLower($hostname)

            RETURN d
            LIMIT 1
            """,
            hostname=hostname
        )

        record = result.single()

        if not record:
            return None

        return dict(record["d"])
    
def get_device_by_ip(ip_address: str):

    with driver.session() as session:

        result = session.run(
            """
            MATCH (d:Device)

            WHERE d.ip_address=$ip

            RETURN d
            LIMIT 5
            """,
            ip=ip_address
        )

        return [
            dict(r["d"])
            for r in result
        ]
    
def get_device_by_serial(serial_number):

    with driver.session() as session:

        result = session.run(
            """
            MATCH (d:Device)

            WHERE d.serial_number=$serial

            RETURN d
            LIMIT 1
            """,
            serial=serial_number
        )

        row = result.single()

        if row:
            return dict(row["d"])

        return None