from django.urls import path
from . import views

app_name = "gifting"

urlpatterns = [
    path("", views.search, name="search"),
    path("create/", views.create, name="create"),
    path("<str:pk>/", views.detail, name="detail"),
    path("<str:pk>/delete/", views.delete, name="delete"),
    path("<str:pk>/edit/", views.edit, name="edit"),
]
