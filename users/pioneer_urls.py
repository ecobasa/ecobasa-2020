from django.urls import path

from . import pioneers

app_name = "pioneers"

urlpatterns = [
    path("", pioneers.pioneer_list, name="list"),
    path("list/", pioneers.api_list, name="api-list"),
    path("markers/", pioneers.api_markers, name="api-markers"),
    path("suggest/", pioneers.api_suggest, name="api-suggest"),
]
