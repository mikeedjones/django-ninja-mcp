from typing import List

import pytest
from ninja import Body, NinjaAPI, Path, Query
from ninja.errors import HttpError

from .types import Item, ItemId, Pagination


@pytest.fixture
def simple_ninja_app() -> NinjaAPI:
    app = NinjaAPI(
        title="Test API",
        description="A test API app for unit testing",
        version="0.1.0",
    )

    items = [
        Item(
            id=1,
            name="Item 1",
            price=10.0,
            tags=["tag1", "tag2"],
            description="Item 1 description",
        ),
        Item(id=2, name="Item 2", price=20.0, tags=["tag2", "tag3"]),
        Item(
            id=3,
            name="Item 3",
            price=30.0,
            tags=["tag3", "tag4"],
            description="Item 3 description",
        ),
    ]

    @app.get("/items", response=List[Item], tags=["items"], operation_id="list_items")
    async def list_items(request, pagination: Query[Pagination]) -> List[Item]:
        """List all items with pagination and sorting options."""
        return items[pagination.skip : pagination.skip + pagination.limit]

    @app.get("/items/{item_id}", response=Item, tags=["items"], operation_id="get_item")
    async def read_item(request, item_id: Path[ItemId]) -> Item:
        """Get a specific item by its ID with optional details."""
        found_item = next((item for item in items if item.id == item_id), None)
        if found_item is None:
            raise HttpError(status_code=404, message="Item not found")
        return found_item

    @app.post("/items", response=Item, tags=["items"], operation_id="create_item")
    async def create_item(
        request,
        item: Item = Body(..., description="The item to create"),
    ) -> Item:
        """Create a new item in the database."""
        items.append(item)
        return item

    @app.put(
        "/items/{item_id}",
        response=Item,
        tags=["items"],
        operation_id="update_item",
    )
    async def update_item(
        request,
        item_id: int = Path(..., description="The ID of the item to update"),
        item: Item = Body(..., description="The updated item data"),
    ) -> Item:
        """Update an existing item."""
        item.id = item_id
        return item

    @app.delete("/items/{item_id}", tags=["items"], operation_id="delete_item")
    async def delete_item(
        request,
        item_id: int = Path(..., description="The ID of the item to delete"),
    ) -> None:
        """Delete an item from the database."""
        return None

    @app.get("/error", tags=["error"], operation_id="raise_error")
    async def raise_error(request) -> None:
        """Fail on purpose and cause a 500 error."""
        raise Exception("This is a test error")

    return app
