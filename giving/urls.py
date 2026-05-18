from django.urls import path
from . import views

app_name = "giving"

urlpatterns = [
    path("", views.request_list, name="list"),
    path("volunteer/<int:pk>/", views.volunteer_detail, name="volunteer_detail"),
    path("action/<str:token>/", views.email_action, name="email_action"),
]
