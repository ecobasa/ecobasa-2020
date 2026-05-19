from django.urls import path
from . import views

app_name = "matches"

urlpatterns = [
    path("",                          views.request_list,      name="list"),
    path("volunteer/<int:pk>/",       views.volunteer_detail,  name="volunteer_detail"),
    path("freemarket/<int:pk>/",      views.adrequest_detail,  name="adrequest_detail"),
    path("skills/<int:pk>/",          views.skillrequest_detail, name="skillrequest_detail"),
    path("action/<str:token>/",       views.email_action,      name="email_action"),
]
