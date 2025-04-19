from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI, Schema

from ninja_mcp import NinjaMCP

api = NinjaAPI()


class Item(Schema):
    id: int
    name: str
    description: str


@api.post("/item", operation_id="update_item")
def hello(request, item: Item):
    return item


mcp = NinjaMCP(api, name="Test MCP Server", description="Test description", base_url="http://localhost:8000")
mcp.mount()

urlpatterns = [path("admin/", admin.site.urls), path("api/", api.urls)]
