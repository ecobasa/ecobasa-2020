from django.urls import path
from . import views

app_name = "gifting"

urlpatterns = [
    path("", views.search, name="search"),
    path("create/", views.create, name="create"),
    path("request/<int:pk>/", views.adrequest_detail, name="adrequest_detail"),
    path("<str:pk>/", views.detail, name="detail"),
    path("<str:pk>/delete/", views.delete, name="delete"),
    path("<str:pk>/edit/", views.edit, name="edit"),
    path("api/markers/",   views.gifting_markers,     name="api-markers"),
    path("api/list/",      views.gifting_list_partial, name="api-list"),
    path("api/suggest/",   views.gifting_suggest,      name="api-suggest"),
    path("api/geocode/",   views.nominatim_proxy,      name="api-geocode"),
]
