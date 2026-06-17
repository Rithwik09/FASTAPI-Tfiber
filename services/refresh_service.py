import asyncio

from cache.status_cache import status_data
from services.status_service import fetch_status


async def refresh_cache():

    while True:

        try:

            print("Refreshing cache...")

            data = fetch_status()

            status_data.clear()
            status_data.extend(data)

            print(
                f"Loaded {len(status_data)} devices"
            )

        except Exception as e:

            print(
                f"Cache refresh failed: {e}"
            )

        await asyncio.sleep(300)