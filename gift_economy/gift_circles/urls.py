from django.urls import path

from . import views

app_name = "gift_circles"

urlpatterns = [
    path("gift-circles/<slug:slug>/giftsheet/", views.giftsheet, name="giftsheet"),
    path("gift-circles/<slug:slug>/giftsheet/entries/<int:pk>/", views.giftsheet_entry, name="giftsheet_entry"),
    path("gift-circles/<slug:slug>/giftsheet/entries/<int:pk>/write/", views.write, name="write"),
    path("gift-circles/<slug:slug>/giftsheet/close/", views.giftsheet_close, name="giftsheet_close"),
    path("gift-circles/<slug:slug>/giftsheet/photos/", views.giftsheet_photo, name="giftsheet_photo"),
    path("gift-circles/<slug:slug>/giftsheet/photos/<int:pk>/delete/", views.giftsheet_photo, name="giftsheet_photo_delete"),
    path("gift-circles/<slug:slug>/giftsheet/print/", views.print_giftsheet, name="print"),
    path("gift-circles/<slug:slug>/next/", views.plan_next, name="next"),
    path("gift-circles/<slug:slug>/stories/", views.story, name="story"),
    path("gift-circles/<slug:slug>/wishes/<str:key>/", views.wishes, name="wishes"),
    path("gift-circles/<slug:slug>/scribes/", views.scribe, name="scribe"),
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
    path("gift-circles/<slug:slug>/guests/<str:token>/giftsheet/", views.guest_giftsheet, name="guest_giftsheet"),
    path("gift-circles/<slug:slug>/guests/<str:token>/giftsheet/print/", views.print_giftsheet, name="guest_print"),
    path(
        "gift-circles/<slug:slug>/guests/<str:token>/giftsheet/entries/<int:pk>/", views.giftsheet_entry,
        name="guest_giftsheet_entry",
    ),
    path(
        "gift-circles/<slug:slug>/guests/<str:token>/giftsheet/entries/<int:pk>/write/", views.guest_write,
        name="guest_write",
    ),
]
