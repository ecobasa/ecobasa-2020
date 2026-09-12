from django.urls import path
from . import views

app_name = "gifts"

urlpatterns = [
    path("", views.search, name="search"),
    path("create/", views.create, name="create"),
    path("<str:pk>/", views.detail, name="detail"),
    path("<str:pk>/delete/", views.delete, name="delete"),
    path("<str:pk>/edit/", views.edit, name="edit"),
    path("api/markers/",   views.gifts_markers,     name="api-markers"),
    path("api/list/",      views.gifts_list_partial, name="api-list"),
    path("api/suggest/",   views.gifts_suggest,      name="api-suggest"),
    path("api/geocode/",   views.nominatim_proxy,      name="api-geocode"),
]
