from django.urls import path
from . import calendar, views

app_name = "matches"

urlpatterns = [
    path("",                    views.matches_list, name="list"),
    path("<int:pk>/",           views.match_detail,  name="detail"),
    path("calendar/<slug:community_slug>/", calendar.calendar, name="calendar"),
    path("lending/",            calendar.lending, name="lending"),
    path("calendar/<slug:community_slug>/covered/", calendar.covered, name="calendar_covered"),
    path("action/<str:token>/", views.email_action,  name="email_action"),
    path("suggestions/<int:pk>/dismiss/",        views.dismiss_suggestion,      name="dismiss_suggestion"),
    path("suggestions/emails/stop/<str:token>/", views.suggestions_unsubscribe, name="suggestions_unsubscribe"),
]
