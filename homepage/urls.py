from django.urls import path
from . import views

app_name = "homepage"

urlpatterns = [
    path("", views.homepage, name="homepage"),
    path("support/", views.support, name="support"),
]
