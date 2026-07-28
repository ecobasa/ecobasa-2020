from django.urls import path
from . import views

app_name = "matches"

urlpatterns = [
    path("",                    views.matches_list, name="list"),
    path("<int:pk>/",           views.match_detail,  name="detail"),
    path("action/<str:token>/", views.email_action,  name="email_action"),
]
