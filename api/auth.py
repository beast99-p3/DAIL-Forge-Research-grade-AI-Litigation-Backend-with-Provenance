"""Simple API-key dependency for the curation (write) endpoints."""

from fastapi import Header, HTTPException, status

from api.config import get_settings


async def require_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    settings = get_settings()
    if x_api_key != settings.CURATION_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return x_api_key
