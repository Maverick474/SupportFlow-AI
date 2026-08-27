from fastapi import HTTPException, Request, status

from controller.resources import AppResources


def get_resources(request: Request) -> AppResources:
    resources = getattr(request.app.state, "resources", None)
    if resources is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backend services are not ready.",
        )
    return resources
