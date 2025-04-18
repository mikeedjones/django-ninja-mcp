from typing import Any, Dict, Optional, Protocol

from pydantic import BaseModel, ConfigDict, JsonValue


class BaseType(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResponseProtocol(Protocol):
    """Protocol defining the interface for HTTP responses."""

    status_code: int
    headers: Dict[str, str]
    content: bytes
    text: str

    def json(self) -> JsonValue: ...

    def raise_for_status(self) -> None: ...


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
    ) -> ResponseProtocol: ...

    async def put(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Any] = None,
    ) -> ResponseProtocol: ...

    async def delete(
        self, url: str, *, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None
    ) -> ResponseProtocol: ...

    async def patch(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Any] = None,
    ) -> ResponseProtocol: ...
