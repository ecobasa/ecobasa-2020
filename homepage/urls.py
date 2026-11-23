from django.urls import path
from . import views

app_name = "homepage"

urlpatterns = [
    path("", views.homepage, name="homepage"),
    path("search/", views.search, name="search"),
    path("support/", views.support, name="support"),
    path("contact/", views.contact, name="contact"),
]
