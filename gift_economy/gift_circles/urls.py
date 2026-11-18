from django.urls import path

from . import views

app_name = "gift_circles"

urlpatterns = [
    path("gift-circles/<slug:slug>/giftsheet/print/", views.print_giftsheet, name="print"),
    path("gift-circles/<slug:slug>/attendee/", views.attendee, name="attendee"),
    path("gift-circles/<slug:slug>/bring/", views.bring, name="bring"),
    path("gift-circles/<slug:slug>/bring/<str:pk>/take-back/", views.take_back, name="take_back"),
    path("gift-circles/<slug:slug>/invite/", views.invite, name="invite"),
    path("gift-circles/<slug:slug>/invite/people/", views.invite_people, name="invite_people"),
    path("gift-circles/<slug:slug>/invitations/<str:token>/", views.invitation, name="invitation"),
    path("gift-circles/<slug:slug>/guests/", views.guest_sign_up, name="guest_sign_up"),
    path("gift-circles/<slug:slug>/guests/<str:token>/", views.guest, name="guest"),
    path("gift-circles/<slug:slug>/guests/<str:token>/confirm/", views.guest_confirm, name="guest_confirm"),
    path("gift-circles/<slug:slug>/guests/<str:token>/account/", views.guest_account, name="guest_account"),
]
