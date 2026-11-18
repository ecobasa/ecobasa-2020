from django.urls import path

from . import views

app_name = "gift_circles"

urlpatterns = [
    path("gift-circles/<slug:slug>/giftsheet/print/", views.print_giftsheet, name="print"),
]
