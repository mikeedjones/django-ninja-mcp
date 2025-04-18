from pydantic import BaseModel, ConfigDict

from typing import Any, Protocol, Optional, Dict


class BaseType(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AsyncClientProtocol(Protocol):
    """Protocol defining the interface for async HTTP clients."""

    async def get(
        self, url: str, *, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None
    ) -> Any: ...

    async def post(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Any] = None,
    ) -> Any: ...

    async def put(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Any] = None,
    ) -> Any: ...

    async def delete(
        self, url: str, *, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None
    ) -> Any: ...

    async def patch(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Any] = None,
    ) -> Any: ...
