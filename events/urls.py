from django.urls import include, path

from . import views

app_name = "events"

# An event's pages live under its host's: /communities/<community>/events/<event>/
community_patterns = [
    path("new/", views.create, name="create"),
    path("<slug:slug>/", views.detail, name="detail"),
    path("<slug:slug>/edit/", views.edit, name="edit"),
    path("<slug:slug>/archive/", views.archive, name="archive"),
    path("<slug:slug>/confirm/", views.confirm, name="confirm"),
    path("<slug:slug>/confirm/<str:token>/", views.confirm_by_email, name="confirm_by_email"),
    path("<slug:slug>/help/", views.offer_help, name="offer_help"),
    path("<slug:slug>/come/", views.come, name="come"),
    path("<slug:slug>/not-coming/", views.not_coming, name="not_coming"),
    path("<slug:slug>/needs/<str:need_pk>/toggle/", views.toggle_need, name="toggle_need"),
]

urlpatterns = [
    # All current events, nearest first, and those one is going to
    path("events/", views.event_list, name="list"),
    path("events/suggest/", views.api_suggest, name="api-suggest"),
    path("events/list/", views.api_list, name="api-list"),
    path("events/markers/", views.api_markers, name="api-markers"),
    path("communities/<slug:community_slug>/events/", include(community_patterns)),
]
