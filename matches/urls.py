from django.urls import path
from . import views

app_name = "matches"

urlpatterns = [
    path("",                    views.matches_list, name="list"),
    path("<int:pk>/",           views.match_detail,  name="detail"),
    path("action/<str:token>/", views.email_action,  name="email_action"),
    path("suggestions/<int:pk>/dismiss/",        views.dismiss_suggestion,      name="dismiss_suggestion"),
    path("suggestions/emails/stop/<str:token>/", views.suggestions_unsubscribe, name="suggestions_unsubscribe"),
]
