# Ninja MCP

[![PyPI version](https://img.shields.io/pypi/v/django-ninja-mcp.svg)](https://pypi.org/project/django-ninja-mcp/)
[![Python Versions](https://img.shields.io/pypi/pyversions/django-ninja-mcp.svg)](https://pypi.org/project/django-ninja-mcp/)
[![License](https://img.shields.io/github/license/mikeedjones/django-ninja-mcp.svg)](https://github.com/mikeedjones/django-ninja-mcp/LICENSE)

Automatic [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server generator for [Django Ninja](https://django-ninja.dev/) applications. Huge credit to [FastAPI-MCP](https://github.com/tadata-org/fastapi_mcp) for the original idea and implementation.

> [!WARNING]
> **This is an early release.** The API is not stable and may change in the future. Please use with caution.

> [!WARNING]
> **This depends on an unmerged addition to Django Ninja.** The `django-ninja-mcp` package depends on a [change to Django Ninja that has not yet been merged](https://github.com/mikeedjones/django-ninja/tree/updated-sse) forked from [@rroblf01's PR.](https://github.com/vitalik/django-ninja/pull/1388).

## What is MCP?

The Model Context Protocol (MCP) is an open protocol that standardizes how applications provide context to Large Language Models (LLMs). Think of MCP like a USB-C port for AI applications - it provides a standardized way to connect AI models to different data sources and tools.

MCP helps you build agents and complex workflows on top of LLMs by providing:
* Pre-built integrations that your LLM can plug into
* Flexibility to switch between LLM providers
* Best practices for securing your data within your infrastructure

## What is Ninja MCP?

Ninja MCP is a library that automatically converts your Django Ninja API endpoints into MCP tools. This allows LLM clients like Claude to interact with your Django application directly through a standardized protocol.

## Features

- **Automatic Tool Generation**: Convert your Django Ninja API endpoints to MCP tools automatically
- **OpenAPI Integration**: Leverages your API's OpenAPI schema for rich tool descriptions
- **SSE Transport**: Built-in Server-Sent Events (SSE) transport for real-time communication
- **Filtering Options**: Include or exclude specific operations or tags
- **Customizable Descriptions**: Control the level of detail in tool descriptions

## Quick Start

Here's a simple example of integrating Ninja MCP with your Django project:

```python
from django.urls import path
from ninja import NinjaAPI
from ninja_mcp import NinjaMCP

# Create your Ninja API as usual
api = NinjaAPI()

@api.get("/hello")
def hello(request):
    return {"message": "Hello, world!"}

@api.get("/greet/{name}")
def greet(request, name: str):
    return {"message": f"Hello, {name}!"}

# Create the MCP server from your API
mcp_server = NinjaMCP(
    ninja=api,
    base_url="http://localhost:8000/api",
    name="My API",
    description="My awesome API with MCP integration"
)

# Mount the MCP server to your API
mcp_server.mount(api, mount_path="/mcp")

# Include in urls.py
urlpatterns = [
    path("api/", api.urls),
]

# update your settings.py to include daphne for handling SSE
INSTALLED_APPS = [
    "daphne",
    ...
    "ninja",
]
```

With this setup, your Django Ninja API is now available as MCP tools at `/api/mcp`. LLM clients that support MCP can connect to this endpoint and use your API's functionality as tools.

For example, with `mcp.client.sse.sse_client` you can connect to the server and call the `/hello` endpoint:

```python
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

async def main():
    async with sse_client("http://localhost:8000/api/mcp") as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            response = await session.call_tool("hello")
```

## MCP Architecture

Your Django application serves as an MCP server that can be connected to by MCP clients (like Claude Desktop). The client-server architecture allows:

1. LLM clients to discover the available tools from your API
2. Tools to be called by the LLM with appropriate parameters
3. Results to be returned to the LLM in a standardized format

## Advanced Usage

### Customizing Tool Generation

```python
mcp_server = NinjaMCP(
    ninja=api,
    base_url="http://localhost:8000/api",
    name="My API",
    description="My awesome API with MCP integration",
    describe_all_responses=True,  # Include all response types in descriptions
    describe_full_response_schema=True,  # Include full response schemas
    include_operations=["get_users", "create_user"],  # Only include specific operations
    # exclude_operations=["delete_user"],  # Exclude specific operations
    include_tags=["users"],  # Only include operations with specific tags
    # exclude_tags=["admin"],  # Exclude operations with specific tags
)
```

### Custom Mount Path

You can mount the MCP server at a custom path:

```python
mcp_server.mount(api, mount_path="/custom/mcp/path")
```

### Mounting to a Different Router

You can mount the MCP server to a different router than the one it was created from:

```python
admin_api = NinjaAPI(urls_namespace="admin")
mcp_server.mount(admin_api, mount_path="/admin/mcp")
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Further Reading

- [MCP Documentation](https://modelcontextprotocol.io/)
- [Django Ninja Documentation](https://django-ninja.dev/)
- [Anthropic Claude Documentation](https://docs.anthropic.com/)