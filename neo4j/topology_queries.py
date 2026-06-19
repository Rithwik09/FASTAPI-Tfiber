from neo4j.connection import driver


def get_upstream_path(device_uid):

    with driver.session() as session:

        result = session.run(
            """
            MATCH path=
            (d:Device{device_uid:$uid})
            -[:CONNECTED_TO*0..10]->
            (root)

            RETURN path
            """,
            uid=device_uid
        )

        return result.data()