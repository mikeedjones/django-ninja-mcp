import json
from logging import getLogger
from typing import Any, Dict, List, Optional, Union

import httpx
import mcp.types as types
from django.http import HttpRequest
from mcp.server.lowlevel.server import Server
from ninja import NinjaAPI, Router
from ninja.openapi import get_schema

from .openapi.convert import convert_openapi_to_mcp_tools
from .transport.sse import NinjaAPISseTransport
from .types import AsyncClientProtocol, ResponseProtocol

logger = getLogger(__name__)


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
        Create an MCP server from a FastAPI app.

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

        self.ninja = ninja
        self.name = name or self.ninja.title or "Ninja MCP"
        self.description = description or self.ninja.description

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
        # Get OpenAPI schema from FastAPI app
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
        Mount the MCP server to **any** NinjaAPI app or Router.

        There is no requirement that the FastAPI app or Router is the same as the one that the MCP
        server was created from.

        Args:
        ----
            router: The FastAPI app or Router to mount the MCP server to. If not provided, the MCP
                    server will be mounted to the FastAPI app.
            mount_path: Path where the MCP server will be mounted

        """
        # Normalize mount path
        if not mount_path.startswith("/"):
            mount_path = f"/{mount_path}"
        if mount_path.endswith("/"):
            mount_path = mount_path[:-1]

        if not router:
            router = self.ninja

        messages_path = f"{mount_path}/messages/"

        sse_transport = NinjaAPISseTransport(messages_path)

        # Route for MCP connection
        @router.get(mount_path, include_in_schema=False, operation_id="mcp_connection")
        async def handle_mcp_connection(request: HttpRequest):
            async with sse_transport.connect_sse(request.scope, request.receive, request._send) as (reader, writer):
                await self.server.run(
                    reader,
                    writer,
                    self.server.create_initialization_options(notification_options=None, experimental_capabilities={}),
                )

        # Route for MCP messages
        @router.post(
            f"{mount_path}/messages/",
            include_in_schema=False,
            operation_id="mcp_messages",
        )
        async def handle_post_message(request: HttpRequest):
            return await sse_transport.handle_fastapi_post_message(request)

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
        except json.JSONDecodeError:
            if hasattr(response, "text"):
                result_text = response.text
            else:
                result_text = response.content

        # If not raising an exception, the MCP server will return the result as a regular text response,
        if response.status_code != 200:
            raise Exception(
                f"Error calling {tool_name}. Status code: {response.status_code}. Response: {response.text}"
            )

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
