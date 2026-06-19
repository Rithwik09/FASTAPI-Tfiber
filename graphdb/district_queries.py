from graphdb.connection import driver


def get_district(district):

    with driver.session() as session:

        result = session.run(
            """
            MATCH (d:District)

            WHERE toLower(d.name)=toLower($district)

            RETURN d
            LIMIT 1
            """,
            district=district
        )

        row = result.single()

        if row:
            return dict(row["d"])

        return None
