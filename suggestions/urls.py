from django.urls import path

from . import views

app_name = "suggestions"

urlpatterns = [
    path("", views.suggestion_list, name="list"),
    path("<int:pk>/dismiss/", views.dismiss, name="dismiss"),
    path("emails/stop/<str:token>/", views.unsubscribe, name="unsubscribe"),
]
