from django.urls import include, path

from . import kinds, views

app_name = "events"


def event_patterns(prefix=""):
    """An event's pages, under its community's address or its kind's own one (named
    "<kind>_detail" etc. there, see Event.url)."""
    return [
        path("new/", views.create, name=f"{prefix}create"),
        path("<slug:slug>/", views.detail, name=f"{prefix}detail"),
        path("<slug:slug>/edit/", views.edit, name=f"{prefix}edit"),
        path("<slug:slug>/archive/", views.archive, name=f"{prefix}archive"),
        path("<slug:slug>/delete/", views.delete, name=f"{prefix}delete"),
        path("<slug:slug>/confirm/", views.confirm, name=f"{prefix}confirm"),
        path("<slug:slug>/confirm/<str:token>/", views.confirm_by_email, name=f"{prefix}confirm_by_email"),
        path("<slug:slug>/help/", views.offer_help, name=f"{prefix}offer_help"),
        path("<slug:slug>/come/", views.come, name=f"{prefix}come"),
        path("<slug:slug>/not-coming/", views.not_coming, name=f"{prefix}not_coming"),
        path("<slug:slug>/needs/<str:need_pk>/toggle/", views.toggle_need, name=f"{prefix}toggle_need"),
    ]


urlpatterns = [
    # All current events, nearest first, and those one is going to
    path("events/", views.event_list, name="list"),
    path("events/going/", views.going, name="going"),
    path("events/suggest/",views.api_suggest, name="api-suggest"),
    path("events/list/", views.api_list, name="api-list"),
    path("events/markers/", views.api_markers, name="api-markers"),
    # Under its community: /communities/<community>/events/<event>/
    path("communities/<slug:community_slug>/events/", include(event_patterns())),
    # Kinds with an address of their own, whoever hosts them: /gift-circles/<event>/
    *(
        path(f"{address}/", include(event_patterns(f"{kind}_")), {"kind": kind})
        for kind, address in kinds.ADDRESSES.items()
    ),
]
