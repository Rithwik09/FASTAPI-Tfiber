from dotenv import load_dotenv
from neo4j import GraphDatabase
import os

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(
        os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER"),
        os.getenv("NEO4J_PASSWORD")
    )
)


def get_driver():
    return driver
