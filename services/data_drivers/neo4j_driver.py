"""
Neo4j driver to fetch devices for different entity types
"""

from graphdb.connection import get_driver


def get_devices_by_district(district_name: str) -> list[str]:
    """
    Get all device hostnames in a district
    
    Cypher:
        MATCH (d:District{name:$district})
        -[:HAS_MANDAL]->(m)
        -[:HAS_LOCATION]->(l)
        -[:HAS_DEVICE]->(dev)
        RETURN collect(dev.hostname)
    """
    driver = get_driver()
    
    with driver.session() as session:
        result = session.run(
            """
            MATCH (d:District{name: $district})
            -[:HAS_MANDAL]->(m)
            -[:HAS_LOCATION]->(l)
            -[:HAS_DEVICE]->(dev)
            RETURN collect(dev.hostname) as hostnames
            """,
            {"district": district_name.upper()}
        )
        
        record = result.single()
        return record["hostnames"] if record else []


def get_devices_by_mandal(mandal_name: str) -> list[str]:
    """
    Get all device hostnames in a mandal
    
    Cypher:
        MATCH (m:Mandal{name:$mandal})
        -[:HAS_LOCATION]->(l)
        -[:HAS_DEVICE]->(dev)
        RETURN collect(dev.hostname)
    """
    driver = get_driver()
    
    with driver.session() as session:
        result = session.run(
            """
            MATCH (m:Mandal{name: $mandal})
            -[:HAS_LOCATION]->(l)
            -[:HAS_DEVICE]->(dev)
            RETURN collect(dev.hostname) as hostnames
            """,
            {"mandal": mandal_name.upper()}
        )
        
        record = result.single()
        return record["hostnames"] if record else []


def get_devices_by_location(location_code: str) -> list[str]:
    """
    Get all device hostnames in a location
    
    Cypher:
        MATCH (l:Location{code:$code})
        -[:HAS_DEVICE]->(dev)
        RETURN collect(dev.hostname)
    """
    driver = get_driver()
    
    with driver.session() as session:
        result = session.run(
            """
            MATCH (l:Location)
            WHERE toLower(coalesce(l.code, "")) = toLower($code)
               OR toLower(coalesce(l.name, "")) = toLower($code)
               OR toString(l.lgd_code) = $code
               OR toString(id(l)) = $code
            MATCH (l)-[:HAS_DEVICE]->(dev)
            RETURN collect(DISTINCT dev.hostname) as hostnames
            """,
            {"code": str(location_code)}
        )
        
        record = result.single()
        return record["hostnames"] if record else []


def get_devices_by_lgd(lgd_code: str) -> list[str]:
    """
    Get all device hostnames by LGD code
    
    Cypher:
        MATCH (l:Location{lgd_code:$code})
        -[:HAS_DEVICE]->(dev)
        RETURN collect(dev.hostname)
    """
    driver = get_driver()
    
    with driver.session() as session:
        result = session.run(
            """
            MATCH (l:Location{lgd_code: $code})
            -[:HAS_DEVICE]->(dev)
            RETURN collect(dev.hostname) as hostnames
            """,
            {"code": lgd_code}
        )
        
        record = result.single()
        return record["hostnames"] if record else []


def get_device_info(hostname: str) -> dict:
    """
    Get device info by hostname
    """
    driver = get_driver()
    
    with driver.session() as session:
        result = session.run(
            """
            MATCH (dev:Device{hostname: $hostname})
            RETURN {
                hostname: dev.hostname,
                ip: dev.ip,
                device_type: dev.device_type,
                location: dev.location,
                vendor: dev.vendor
            } as info
            """,
            {"hostname": hostname.upper()}
        )
        
        record = result.single()
        return record["info"] if record else {}


def get_services_for_device(hostname: str) -> list[str]:
    """
    Get all services that depend on this device
    
    Cypher:
        MATCH (dev:Device{hostname:$hostname})
        <-[:USES_DEVICE]-(s:Service)
        RETURN collect(s.service_id)
    """
    driver = get_driver()
    
    with driver.session() as session:
        result = session.run(
            """
            MATCH (dev:Device{hostname: $hostname})
            <-[:USES_DEVICE]-(s:Service)
            RETURN collect(s.service_id) as services
            """,
            {"hostname": hostname.upper()}
        )
        
        record = result.single()
        return record["services"] if record else []


def get_users_for_service(service_id: str) -> int:
    """
    Get count of users for a service
    """
    driver = get_driver()
    
    with driver.session() as session:
        result = session.run(
            """
            MATCH (s:Service{service_id: $service_id})
            <-[:SUBSCRIBED_TO]-(u:User)
            RETURN count(u) as user_count
            """,
            {"service_id": service_id}
        )
        
        record = result.single()
        return record["user_count"] if record else 0
