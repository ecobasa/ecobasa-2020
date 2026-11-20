from django.urls import path

from . import views

app_name = "help"

urlpatterns = [
    path("", views.index, name="index"),
    path("community-tours/", views.tours, name="tours"),
    path("community-tours/travelling-tips/", views.travelling_tips, name="travelling_tips"),
    path("members/", views.members, name="members"),
    path("gift-circles/", views.gift_circles, name="gift_circles"),
]
