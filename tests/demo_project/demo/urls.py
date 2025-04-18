from django.contrib import admin
from django.urls import include, path
from ninja import NinjaAPI

from ninja_mcp import NinjaMCP

api = NinjaAPI()

mcp = NinjaMCP(api, name="Test MCP Server", description="Test description", base_url="http://localhost:8000")
mcp.mount()

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("events/", include("django_eventstream.urls")),
]
