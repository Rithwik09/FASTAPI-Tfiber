from graphdb.connection import driver


def get_district(district_name: str):
    """Get district by name"""
    with driver.session() as session:
        result = session.run(
            """
            MATCH (d:District)
            WHERE toLower(d.name)=toLower($name)
            RETURN d
            LIMIT 1
            """,
            name=district_name
        )
        row = result.single()
        if row:
            return dict(row["d"])
        return None


def get_mandal(mandal_name: str):
    """Get mandal by name (canonical Location type for mandal level)"""
    with driver.session() as session:
        result = session.run(
            """
            MATCH (m:Mandal)
            WHERE toLower(m.name)=toLower($name)
            RETURN m
            LIMIT 1
            """,
            name=mandal_name
        )
        row = result.single()
        if row:
            return dict(row["m"])
        return None


def get_location_by_lgd(lgd_code: str):
    """Get location by LGD code (canonical mapping for LGD)"""
    with driver.session() as session:
        result = session.run(
            """
            MATCH (l:Location)
            WHERE l.lgd_code=$code
            RETURN l
            LIMIT 1
            """,
            code=lgd_code
        )
        row = result.single()
        if row:
            return dict(row["l"])
        return None


def get_location_by_code(location_code: str):
    """Get location by location code"""
    with driver.session() as session:
        result = session.run(
            """
            MATCH (l:Location)
            WHERE toLower(l.code)=toLower($code)
            RETURN l
            LIMIT 1
            """,
            code=location_code
        )
        row = result.single()
        if row:
            return dict(row["l"])
        return None
