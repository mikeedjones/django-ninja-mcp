"""
Django Ninja MCP Integration Module.

This module provides integration between Django Ninja and the Model Context Protocol (MCP).
It converts Django Ninja API routes into MCP tools that can be used by MCP clients.

Example usage:
```python
from django.urls import path
from ninja import NinjaAPI
from ninja_mcp import NinjaMCP

api = NinjaAPI()


@api.get("/hello")
def hello(request):
    return {"message": "Hello, world!"}


# Create the MCP server
mcp_server = NinjaMCP(ninja=api, base_url="http://localhost:8000/api", name="My API", description="My awesome API")

# Mount the MCP server to the Ninja API
mcp_server.mount(api, mount_path="/mcp")

urlpatterns = [
    path("api/", api.urls),
]
```

This will make your Django Ninja API available as MCP tools at /api/mcp.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

import httpx
import mcp.types as types
from django.http import HttpResponse
from mcp.server.lowlevel.server import Server
from ninja import Body, NinjaAPI, Path, Router
from ninja.openapi import get_schema

from .openapi.convert import convert_openapi_to_mcp_tools
from .transport.sse import DjangoSseServerTransport
from .types import AsyncClientProtocol, ResponseProtocol

logger = logging.getLogger(__name__)


class NinjaMCP:
    def __init__(
        self,
        ninja: NinjaAPI,
        base_url: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        describe_all_responses: bool = False,
        describe_full_response_schema: bool = False,
        http_client: Optional[AsyncClientProtocol] = None,
        include_operations: Optional[List[str]] = None,
        exclude_operations: Optional[List[str]] = None,
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
    ):
        """
        Create an MCP server from a Django Ninja API.

        Args:
        ----
            ninja: The NinjaAPI application
            name: Name for the MCP server (defaults to app.title)
            description: Description for the MCP server (defaults to app.description)
            base_url: Base URL for API requests.
            describe_all_responses: Whether to include all possible response schemas in tool descriptions
            describe_full_response_schema: Whether to include full json schema for responses in tool descriptions
            http_client: Optional HTTP client to use for API calls. If not provided,
                a new httpx.AsyncClient will be created. This is primarily for testing purposes.
            include_operations: List of operation IDs to include as MCP tools. Cannot be used with exclude_operations.
            exclude_operations: List of operation IDs to exclude from MCP tools. Cannot be used with include_operations.
            include_tags: List of tags to include as MCP tools. Cannot be used with exclude_tags.
            exclude_tags: List of tags to exclude from MCP tools. Cannot be used with include_tags.

        """
        # Validate operation and tag filtering options
        if include_operations is not None and exclude_operations is not None:
            raise ValueError("Cannot specify both include_operations and exclude_operations")

        if include_tags is not None and exclude_tags is not None:
            raise ValueError("Cannot specify both include_tags and exclude_tags")

        self.operation_map: Dict[str, Dict[str, Any]]
        self.tools: List[types.Tool]
        self.server: Server
        self.sse_transport: Optional[DjangoSseServerTransport] = None

        self.ninja = ninja
        self.name = name or getattr(self.ninja, "title", None) or "Ninja MCP"
        self.description = description or getattr(self.ninja, "description", None)

        self._base_url = base_url
        self._describe_all_responses = describe_all_responses
        self._describe_full_response_schema = describe_full_response_schema
        self._include_operations = include_operations
        self._exclude_operations = exclude_operations
        self._include_tags = include_tags
        self._exclude_tags = exclude_tags

        self._http_client = http_client or httpx.AsyncClient()

        self.setup_server()

    def setup_server(self) -> None:
        """Initialize the MCP server with tools converted from the OpenAPI schema."""
        # Get OpenAPI schema from Django Ninja API
        openapi_schema = get_schema(api=self.ninja, path_prefix="")

        # Convert OpenAPI schema to MCP tools
        all_tools, self.operation_map = convert_openapi_to_mcp_tools(
            openapi_schema,
            describe_all_responses=self._describe_all_responses,
            describe_full_response_schema=self._describe_full_response_schema,
        )

        # Filter tools based on operation IDs and tags
        self.tools = self._filter_tools(all_tools, openapi_schema)

        # Normalize base URL
        if self._base_url.endswith("/"):
            self._base_url = self._base_url[:-1]

        # Create the MCP lowlevel server
        mcp_server: Server = Server(self.name, self.description)

        # Register handlers for tools
        @mcp_server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            return self.tools

        # Register the tool call handler
        @mcp_server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Dict[str, Any]
        ) -> List[Union[types.TextContent, types.ImageContent, types.EmbeddedResource]]:
            return await self._execute_api_tool(
                client=self._http_client,
                base_url=self._base_url or "",
                tool_name=name,
                arguments=arguments,
                operation_map=self.operation_map,
            )

        self.server = mcp_server

    def mount(self, router: Optional[NinjaAPI | Router] = None, mount_path: str = "/mcp") -> None:
        """
        Mount the MCP server to a Django Ninja API or Router.

        There is no requirement that the Ninja API or Router is the same as the one that the MCP
        server was created from.

        Args:
        ----
            router: The Ninja API or Router to mount the MCP server to. If not provided, the MCP
                    server will be mounted to the Ninja API used to create the MCP server.
            mount_path: Path where the MCP server will be mounted

        """
        # Normalize mount path
        if not mount_path.startswith("/"):
            mount_path = f"/{mount_path}"
        if mount_path.endswith("/"):
            mount_path = mount_path[:-1]

        if not router:
            router = self.ninja

        # Build the base path correctly for the SSE transport
        base_path = ""

        # Create the SSE transport
        self.sse_transport = DjangoSseServerTransport(f"{base_path}{mount_path}/messages/", self.server)

        # Define the SSE connection endpoint
        @router.event_source(mount_path, include_in_schema=False, operation_id="mcp_connection")
        async def handle_mcp_connection(request):
            """Handle SSE connection for MCP clients."""
            async for event in self.sse_transport.connect_sse(request):
                yield event

        # Define the endpoint for receiving messages from clients
        @router.post("/{session_id}", include_in_schema=False, response=Dict[str, Any], operation_id="mcp_messages")
        async def handle_post_message(
            request, session_id: Path[UUID], message: Body[types.JSONRPCMessage]
        ) -> HttpResponse:
            """Handle POST messages from MCP clients."""
            return await self.sse_transport.handle_post_message(session_id, message)

        logger.info(f"MCP server listening at {mount_path}")

    async def _execute_api_tool(
        self,
        client: AsyncClientProtocol,
        base_url: str,
        tool_name: str,
        arguments: Dict[str, Any],
        operation_map: Dict[str, Dict[str, Any]],
    ) -> List[Union[types.TextContent, types.ImageContent, types.EmbeddedResource]]:
        """
        Execute an MCP tool by making an HTTP request to the corresponding API endpoint.

        Args:
        ----
            base_url: The base URL for the API
            tool_name: The name of the tool to execute
            arguments: The arguments for the tool
            operation_map: A mapping from tool names to operation details
            client: Optional HTTP client to use (primarily for testing)

        Returns:
        -------
            The result as MCP content types

        """
        if tool_name not in operation_map:
            raise Exception(f"Unknown tool: {tool_name}")

        operation = operation_map[tool_name]
        path: str = operation["path"]
        method: str = operation["method"]
        parameters: List[Dict[str, Any]] = operation.get("parameters", [])
        arguments = arguments.copy() if arguments else {}  # Deep copy arguments to avoid mutating the original

        url = f"{base_url}{path}"
        for param in parameters:
            if param.get("in") == "path" and param.get("name") in arguments:
                param_name = param.get("name", None)
                if param_name is None:
                    raise ValueError(f"Parameter name is None for parameter: {param}")
                url = url.replace(f"{{{param_name}}}", str(arguments.pop(param_name)))

        query = {}
        for param in parameters:
            if param.get("in") == "query" and param.get("name") in arguments:
                param_name = param.get("name", None)
                if param_name is None:
                    raise ValueError(f"Parameter name is None for parameter: {param}")
                query[param_name] = arguments.pop(param_name)

        headers = {}
        for param in parameters:
            if param.get("in") == "header" and param.get("name") in arguments:
                param_name = param.get("name", None)
                if param_name is None:
                    raise ValueError(f"Parameter name is None for parameter: {param}")
                headers[param_name] = arguments.pop(param_name)

        body = arguments if arguments else None

        logger.debug(f"Making {method.upper()} request to {url}")
        response = await self._request(client, method, url, query, headers, body)

        try:
            result = response.json()
            result_text = json.dumps(result, indent=2)
        except (json.JSONDecodeError, AttributeError):
            if hasattr(response, "text"):
                result_text = response.text
            else:
                result_text = str(response.content)

        # Return an error message if the request was not successful
        if response.status_code >= 400:
            raise Exception(f"Error calling {tool_name}. Status code: {response.status_code}. Response: {result_text}")

        return [types.TextContent(type="text", text=result_text)]

    async def _request(
        self,
        client: AsyncClientProtocol,
        method: str,
        url: str,
        query: Dict[str, Any],
        headers: Dict[str, str],
        body: Optional[Any],
    ) -> ResponseProtocol:
        """Make the actual HTTP request."""
        if method.lower() == "get":
            return await client.get(url, params=query, headers=headers)
        elif method.lower() == "post":
            return await client.post(url, params=query, headers=headers, json=body)
        elif method.lower() == "put":
            return await client.put(url, params=query, headers=headers, json=body)
        elif method.lower() == "delete":
            return await client.delete(url, params=query, headers=headers)
        elif method.lower() == "patch":
            return await client.patch(url, params=query, headers=headers, json=body)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

    def _filter_tools(self, tools: List[types.Tool], openapi_schema: Dict[str, Any]) -> List[types.Tool]:
        """
        Filter tools based on operation IDs and tags.

        Args:
        ----
            tools: List of tools to filter
            openapi_schema: The OpenAPI schema

        Returns:
        -------
            Filtered list of tools

        """
        if (
            self._include_operations is None
            and self._exclude_operations is None
            and self._include_tags is None
            and self._exclude_tags is None
        ):
            return tools

        operations_by_tag: Dict[str, List[str]] = {}
        for path, path_item in openapi_schema.get("paths", {}).items():
            for method, operation in path_item.items():
                if method not in ["get", "post", "put", "delete", "patch"]:
                    continue

                operation_id = operation.get("operationId")
                if not operation_id:
                    continue

                tags = operation.get("tags", [])
                for tag in tags:
                    if tag not in operations_by_tag:
                        operations_by_tag[tag] = []
                    operations_by_tag[tag].append(operation_id)

        operations_to_include = set()

        if self._include_operations is not None:
            operations_to_include.update(self._include_operations)
        elif self._exclude_operations is not None:
            all_operations = {tool.name for tool in tools}
            operations_to_include.update(all_operations - set(self._exclude_operations))

        if self._include_tags is not None:
            for tag in self._include_tags:
                operations_to_include.update(operations_by_tag.get(tag, []))
        elif self._exclude_tags is not None:
            excluded_operations = set()
            for tag in self._exclude_tags:
                excluded_operations.update(operations_by_tag.get(tag, []))

            all_operations = {tool.name for tool in tools}
            operations_to_include.update(all_operations - excluded_operations)

        filtered_tools = [tool for tool in tools if tool.name in operations_to_include]

        if filtered_tools:
            filtered_operation_ids = {tool.name for tool in filtered_tools}
            self.operation_map = {
                op_id: details for op_id, details in self.operation_map.items() if op_id in filtered_operation_ids
            }

        return filtered_tools
