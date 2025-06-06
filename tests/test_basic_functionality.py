import pytest
from mcp.server.lowlevel.server import Server
from ninja import NinjaAPI

from ninja_mcp import NinjaMCP


def test_create_mcp_server(simple_ninja_app: NinjaAPI):
    """Test creating an MCP server without mounting it."""
    mcp = NinjaMCP(
        simple_ninja_app, name="Test MCP Server", description="Test description", base_url="http://localhost:8000"
    )

    # Verify the MCP server was created correctly
    assert mcp.name == "Test MCP Server"
    assert mcp.description == "Test description"
    assert mcp._base_url == "http://localhost:8000"
    assert isinstance(mcp.server, Server)
    assert len(mcp.tools) > 0, "Should have extracted tools from the app"
    assert len(mcp.operation_map) > 0, "Should have operation mapping"

    # Check that the operation map contains all expected operations from simple_app
    expected_operations = ["list_items", "get_item", "create_item", "update_item", "delete_item", "raise_error"]
    for op in expected_operations:
        assert op in mcp.operation_map, f"Operation {op} not found in operation map"


def test_default_values(simple_ninja_app: NinjaAPI):
    """Test that default values are used when not explicitly provided."""
    mcp = NinjaMCP(simple_ninja_app, base_url="http://localhost:8000")

    # Verify default values
    assert mcp.name == simple_ninja_app.title
    assert mcp.description == simple_ninja_app.description

    # Mount with default path
    mcp.mount()

    # Check that the MCP server was properly mounted
    # Look for a route that includes our mount path in its pattern
    routes, _, _ = simple_ninja_app.urls
    assert any(route.pattern.regex.match("mcp") for route in routes), "MCP server mount point not found in app routes"


@pytest.mark.parametrize(
    "mount_path,expected_path",
    [
        ("test-mcp", "test-mcp"),  # No leading slash
        ("/test-mcp2/", "test-mcp2"),  # With leading and trailing slashes
    ],
)
def test_normalize_paths(simple_ninja_app: NinjaAPI, mount_path: str, expected_path: str):
    """Test that mount paths are normalized correctly."""
    mcp = NinjaMCP(simple_ninja_app, base_url="http://localhost:8000")

    # Mount with the test path
    mcp.mount(mount_path=mount_path)

    # Check that the route was added with a normalized path
    assert any(
        route.pattern.regex.match(expected_path) for route in simple_ninja_app.urls[0]
    ), f"Normalized mount path {expected_path} not found in app routes"
