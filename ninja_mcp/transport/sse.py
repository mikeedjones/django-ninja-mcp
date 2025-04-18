"""
Django SSE Server Transport Module.

This module implements a Server-Sent Events (SSE) transport layer for MCP servers
integrated with Django and Django Ninja.

Example usage:
```python
    # Create an SSE transport at an endpoint
    sse_transport = DjangoSseServerTransport("/mcp/messages/")

    @router.get("/mcp", include_in_schema=False)
    async def handle_mcp_connection(request: HttpRequest):
        return await sse_transport.connect_sse(request)

    @router.post("/mcp/messages/", include_in_schema=False)
    async def handle_post_message(request: HttpRequest):
        return await sse_transport.handle_post_message(request)
```

The transport manages bidirectional communication:
- Server-to-client via SSE streams
- Client-to-server via POST requests containing JSON-RPC messages
"""

import asyncio
import logging
from typing import Dict
from uuid import UUID, uuid4

import anyio
import mcp.types as types
from anyio.streams.memory import MemoryObjectSendStream
from django.http import HttpRequest, HttpResponse, JsonResponse
from mcp.server.lowlevel.server import Server

logger = logging.getLogger(__name__)


class DjangoSseServerTransport:
    """
    SSE server transport for MCP that works with Django and Django Ninja.

    This class provides two main functions:

    1. connect_sse() - Sets up a new SSE stream to send server messages to the client
    2. handle_post_message() - Receives incoming POST requests with client messages
       that link to a previously established SSE session
    """

    _endpoint: str
    _read_stream_writers: Dict[UUID, MemoryObjectSendStream[types.JSONRPCMessage | Exception]]
    _write_tasks: Dict[UUID, asyncio.Task]

    def __init__(self, endpoint: str, server: Server) -> None:
        """
        Create a new SSE server transport for Django.

        Args:
        ----
            endpoint: The endpoint path where client POST messages should be sent.
                     This can be relative or absolute.
            server: The MCP server instance that will handle the messages.

        """
        super().__init__()
        self._endpoint = endpoint
        self._server = server
        self._read_stream_writers = {}
        self._write_tasks = {}
        logger.debug(f"DjangoSseServerTransport initialized with endpoint: {endpoint}")

    def connect_sse(self, request: HttpRequest) -> HttpResponse:
        """
        Handle an incoming SSE connection request.

        This method sets up the SSE stream and returns the Django response that
        will stream events to the client.

        Args:
        ----
            request: The Django HttpRequest object

        Returns:
        -------
            An HttpResponse that streams SSE events to the client

        """
        logger.debug("Setting up SSE connection")

        # Create a unique session ID for this connection
        session_id = uuid4()
        channel_name = f"mcp-{session_id.hex}"

        # Create streams for bidirectional communication
        read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
        write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

        # Store the writer for later use by POST handlers
        self._read_stream_writers[session_id] = read_stream_writer

        # Prepare the session URI that clients will use for POSTing messages
        logger.debug(f"Created new session with ID: {session_id}, channel: {channel_name}")

        # Set up a task to forward messages from write_stream to the SSE channel
        async def sse_writer():
            try:
                logger.debug(f"Starting SSE writer for session {session_id}")
                # Send the endpoint info as the first event
                yield f"event: endpoint\ndata: {session_id}\n\n"
                logger.debug(f"Sent endpoint event: {session_id}")

                # Then listen for messages and forward them as SSE events
                async with write_stream_reader:
                    async for message in write_stream_reader:
                        logger.debug(f"Sending message via SSE: {message}")
                        yield f"event: message\ndata: {message.model_dump_json()}\n\n"
            except Exception as e:
                logger.error(f"Error in SSE writer: {e}")
            finally:
                # Clean up when the connection is closed
                if session_id in self._read_stream_writers:
                    del self._read_stream_writers[session_id]
                logger.debug(f"SSE writer for session {session_id} has ended")

        # Start the MCP server with the streams
        async def run_mcp_server():
            try:
                await self._server.run(read_stream, write_stream, self._server.create_initialization_options())
            finally:
                # Clean up when the server is done
                if session_id in self._write_tasks:
                    self._write_tasks[session_id].cancel()
                    del self._write_tasks[session_id]

                await write_stream.aclose()
                await read_stream.aclose()

        # Start the asyncio task to run the MCP server
        asyncio.create_task(run_mcp_server())

        return sse_writer()

    async def handle_post_message(self, session_id: UUID, message: types.JSONRPCMessage) -> HttpResponse:
        """
        Handle an incoming POST message from a client.

        This method processes the JSON-RPC message and forwards it to the appropriate
        session's read stream.

        Args:
        ----
            session_id: The ID of the session to which the message belongs
            message: The JSON-RPC message to be sent

        Returns:
        -------
            An HttpResponse indicating success or failure

        """
        # Find the appropriate write stream for this session
        writer = self._read_stream_writers.get(session_id)
        if not writer:
            logger.warning(f"Could not find session for ID: {session_id}")
            return JsonResponse({"error": "Could not find session"}, status=404)

        asyncio.create_task(writer.send(message))

        # Return success response
        return JsonResponse({"status": "Accepted"}, status=202)
