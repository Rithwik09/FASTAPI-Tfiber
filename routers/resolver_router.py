from fastapi import APIRouter

from services.resolver_service import (
    resolve_entity
)

router = APIRouter(
    prefix="/resolve",
    tags=["resolver"]
)

@router.post("/")
def resolve(request: dict):

    return resolve_entity(
        request["query"]
    )