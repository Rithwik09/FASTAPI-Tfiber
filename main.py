from dotenv import load_dotenv
load_dotenv()

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

from services.topology_data import topo
from services.refresh_service import refresh_cache

from routers.status_router import router as status_router
from routers.bandwidth_router import router as bandwidth_router
from services.topology_router import topology_router

from routers.resolver_router import (
    router as resolver_router
)

@asynccontextmanager
async def lifespan(app: FastAPI):

    await asyncio.get_event_loop().run_in_executor(
        None,
        topo.load
    )

    asyncio.create_task(
        refresh_cache()
    )

    yield


app = FastAPI(
    title="TFiber Status Engine",
    description="Comprehensive network status and monitoring API",
    version="2.0.0"
)

# Core routers
app.include_router(status_router)
app.include_router(bandwidth_router)
app.include_router(topology_router)
app.include_router(resolver_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )