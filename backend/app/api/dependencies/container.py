from fastapi import Request
from app.service.container import ServiceContainer


def get_container(request: Request) -> ServiceContainer:
    """FastAPI dependency — returns the ServiceContainer from app.state."""
    return request.app.state.container
