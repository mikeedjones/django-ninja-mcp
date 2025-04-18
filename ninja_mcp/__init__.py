"""
Ninja-MCP: Automatic MCP server generator for Django Ninja applications.
"""

try:
    from importlib.metadata import version

    __version__ = version("django-ninja-mcp")
except Exception:
    # Fallback for local development
    __version__ = "0.0.0.dev0"

from .server import NinjaMCP

__all__ = [
    "NinjaMCP",
]
