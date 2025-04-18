from json import loads as json_loads
from typing import Any, Callable, Dict, Optional, Union
from unittest.mock import Mock
from urllib.parse import urljoin

from django.http import QueryDict, StreamingHttpResponse
from django.http.request import HttpHeaders, HttpRequest
from ninja.responses import Response as HttpResponse
from ninja.testing.client import NinjaClientBase


def build_absolute_uri(location: Optional[str] = None) -> str:
    base = "http://testlocation/"

    if location:
        base = urljoin(base, location)

    return base


# TODO: this should be changed
# maybe add here urlconf object and add urls from here
class NinjaMCPClientBase(NinjaClientBase):
    __test__ = False  # <- skip pytest

    def _build_request(self, method: str, path: str, data: Dict, request_params: Any) -> Mock:
        request = Mock(spec=HttpRequest)
        request.method = method
        request.path = path
        request.body = ""
        request.COOKIES = {}
        request._dont_enforce_csrf_checks = True
        request.is_secure.return_value = False
        request.build_absolute_uri = build_absolute_uri

        request.auth = None
        request.user = Mock()
        if "user" not in request_params:
            request.user.is_authenticated = False
            request.user.is_staff = False
            request.user.is_superuser = False

        request.META = request_params.pop("META", {"REMOTE_ADDR": "127.0.0.1"})
        request.FILES = request_params.pop("FILES", {})

        request.META.update({f"HTTP_{k.replace('-', '_')}": v for k, v in request_params.pop("headers", {}).items()})

        request.headers = HttpHeaders(request.META)

        if isinstance(data, QueryDict):
            request.POST = data
        else:
            request.POST = QueryDict(mutable=True)

            if isinstance(data, (str, bytes)):
                request_params["body"] = data
            elif data:
                for k, v in data.items():
                    request.POST[k] = v

        if "?" in path:
            request.GET = QueryDict(path.split("?")[1])
        else:
            query_params = request_params.pop("query_params", request_params.pop("params", None))
            if query_params:
                query_dict = QueryDict(mutable=True)
                for k, v in query_params.items():
                    if isinstance(v, list):
                        for item in v:
                            query_dict.appendlist(k, item)
                    else:
                        query_dict[k] = v
                request.GET = query_dict
            else:
                request.GET = QueryDict()

        for k, v in request_params.items():
            setattr(request, k, v)
        return request


class NinjaResponse:
    content_stream = None

    def __init__(self, http_response: Union[HttpResponse, StreamingHttpResponse]):
        self._response = http_response
        self.status_code = http_response.status_code
        self.streaming = http_response.streaming
        if self.streaming:
            self.content_stream = http_response.streaming_content
        else:
            self.content = http_response.content  # type: ignore[union-attr]
        self._data = None

    def json(self) -> Any:
        return json_loads(self.content)

    @property
    def data(self) -> Any:
        if self._data is None:  # Recomputes if json() is None but cheap then
            self._data = self.json()
        return self._data

    def __getitem__(self, key: str) -> Any:
        return self._response[key]

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._response, attr)


class TestAsyncClient(NinjaMCPClientBase):
    async def _call(self, func: Callable, request: Mock, kwargs: Dict) -> "NinjaResponse":
        return NinjaResponse(await func(request, **kwargs))


class TestClient(NinjaMCPClientBase):
    def _call(self, func: Callable, request: Mock, kwargs: Dict) -> "NinjaResponse":
        return NinjaResponse(func(request, **kwargs))
