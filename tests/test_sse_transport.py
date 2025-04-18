import re

import pytest
from mcp import types
from ninja import NinjaAPI

from ninja_mcp import NinjaMCP
from ninja_mcp.testing import TestAsyncClient, TestClient


@pytest.fixture
def ninja_app_with_sse(simple_ninja_app: NinjaAPI):
    """Create an MCP server with SSE transport configured."""
    mcp = NinjaMCP(
        simple_ninja_app, name="Test MCP Server", description="Test description", base_url="http://testserver"
    )
    mcp.mount()
    return simple_ninja_app


@pytest.mark.asyncio
async def test_sse_connection_establishment(ninja_app_with_sse):
    """Test establishing an SSE connection."""
    mock_client = TestClient(ninja_app_with_sse)

    # Connect to the SSE endpoint
    events = []
    async for event in mock_client.get("/mcp").content_stream:
        events.append(event)
        if "endpoint" in event.decode("utf-8"):
            break
    else:
        pytest.fail("Failed to establish SSE connection")

    # Verify we received the connection events
    assert len(events) >= 1


@pytest.mark.asyncio
async def test_message_sending(ninja_app_with_sse):
    """Test sending a message via the SSE transport."""
    async_mock_client = TestAsyncClient(ninja_app_with_sse)
    mock_client = TestClient(ninja_app_with_sse)

    # Connect to the SSE endpoint
    events = []
    async for event in mock_client.get("/mcp").content_stream:
        events.append(event)
        if "endpoint" in event.decode("utf-8"):
            break
    else:
        pytest.fail("Failed to establish SSE connection")

    endpoint = re.search(r"(?<=data: )\S+", events[0].decode("utf-8")).group(0)

    # Send an initialization message
    response = await async_mock_client.post(
        endpoint,
        data=types.JSONRPCRequest(
            id="init-1",
            method="initialize",
            params=types.InitializeRequestParams(
                protocolVersion=types.LATEST_PROTOCOL_VERSION,
                capabilities=types.ClientCapabilities(),
                clientInfo=types.Implementation(name="test-client", version="1.0.0"),
            ).model_dump(by_alias=True, exclude_none=True),
            jsonrpc="2.0",
        ).model_dump_json(),
        content_type="application/json",
    )

    # Verify the response
    assert response.status_code == 202
