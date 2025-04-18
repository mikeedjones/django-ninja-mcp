import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Tuple
from uuid import UUID, uuid4

import anyio
import mcp.types as types
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from django.http import HttpResponse, JsonResponse
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class DjangoSseServerTransport:
    """
    SSE server transport for MCP that works with Django Ninja.

    Provides two endpoints:
    1. connect_sse() - Handles SSE connection establishment
    2. handle_post_message() - Processes incoming messages from clients
    """

    def __init__(self, endpoint_path: str) -> None:
        """
        Create a new SSE server transport.

        Args:
        ----
            endpoint_path: The URL path where clients should POST messages

        """
        self._endpoint = endpoint_path
        self._read_stream_writers = {}
        logger.debug(f"DjangoSseServerTransport initialized with endpoint: {endpoint_path}")

    @asynccontextmanager
    async def connect_sse(
        self, request
    ) -> AsyncGenerator[Tuple[MemoryObjectReceiveStream, MemoryObjectSendStream], None]:
        """
        Set up an SSE connection for a client.

        This method should be called from a Django Ninja endpoint that's
        configured to use Daphne or another ASGI server.
        """
        # Create memory streams for communication
        read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
        write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

        # Create a unique session ID and store the write stream
        session_id = uuid4()
        session_uri = f"{self._endpoint}?session_id={session_id.hex}"
        self._read_stream_writers[session_id] = read_stream_writer
        logger.debug(f"Created new session with ID: {session_id}")

        # Create streams for SSE events
        sse_stream_writer, sse_stream_reader = anyio.create_memory_object_stream[Dict[str, Any]](0)

        async def sse_writer():
            logger.debug("Starting SSE writer")
            async with sse_stream_writer, write_stream_reader:
                # Send the endpoint URL to the client
                await sse_stream_writer.send({"event": "endpoint", "data": session_uri})
                logger.debug(f"Sent endpoint event: {session_uri}")

                # Forward messages to the client
                async for message in write_stream_reader:
                    logger.debug(f"Sending message via SSE: {message}")
                    await sse_stream_writer.send(
                        {
                            "event": "message",
                            "data": message.model_dump_json(by_alias=True, exclude_none=True),
                        }
                    )

        # Set up the SSE response
        async def sse_response_generator():
            yield "event: connected\ndata: connected\n\n"
            yield f"event: endpoint\ndata: {session_uri}\n\n"

            async with anyio.create_task_group() as tg:
                tg.start_soon(sse_writer)

                async for event in sse_stream_reader:
                    event_type = event.get("event", "message")
                    data = event.get("data", "")
                    if isinstance(data, dict):
                        data = json.dumps(data)

                    yield f"event: {event_type}\ndata: {data}\n\n"

        try:
            # Start the SSE response in the background
            response = HttpResponse(sse_response_generator(), content_type="text/event-stream")
            response["Cache-Control"] = "no-cache"
            response["Connection"] = "keep-alive"

            # Yield the streams for the MCP server to use
            yield (read_stream, write_stream)
        finally:
            # Clean up
            if session_id in self._read_stream_writers:
                del self._read_stream_writers[session_id]

    async def handle_post_message(self, request, session_id: str):
        """
        Handle an incoming message from a client.

        This should be exposed as a Django Ninja API endpoint.
        """
        logger.debug("Handling POST message")

        # Validate the session ID
        try:
            uuid_session_id = UUID(hex=session_id)
            logger.debug(f"Parsed session ID: {uuid_session_id}")
        except ValueError:
            logger.warning(f"Received invalid session ID: {session_id}")
            return JsonResponse({"error": "Invalid session ID"}, status=400)

        # Find the associated stream writer
        writer = self._read_stream_writers.get(uuid_session_id)
        if not writer:
            logger.warning(f"Could not find session for ID: {uuid_session_id}")
            return JsonResponse({"error": "Could not find session"}, status=404)

        # Parse the message
        try:
            body = await request.body()
            logger.debug(f"Received JSON: {body}")
            message = types.JSONRPCMessage.model_validate_json(body)
            logger.debug(f"Validated client message: {message}")
        except ValidationError as err:
            logger.error(f"Failed to parse message: {err}")
            await writer.send(err)
            return JsonResponse({"error": "Could not parse message"}, status=400)

        # Send the message to the server
        logger.debug(f"Sending message to writer: {message}")
        await writer.send(message)
        return JsonResponse({"status": "accepted"}, status=202)
