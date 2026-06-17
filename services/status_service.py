import requests
from requests.auth import HTTPBasicAuth

URL = "http://tfdcosssm1.tfiber.in:14081/status"

USERNAME = "Tfiber"
PASSWORD = "Tfiber@2024"

def fetch_status():

    response = requests.get(
        URL,
        auth=HTTPBasicAuth(USERNAME, PASSWORD),
        timeout=120
    )

    response.raise_for_status()

    return response.json()