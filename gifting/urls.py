from django.urls import path
from . import views

app_name = "gifting"

urlpatterns = [
    path("", views.search, name="search"),
    path("<str:pk>", views.detail, name="detail"),
]
