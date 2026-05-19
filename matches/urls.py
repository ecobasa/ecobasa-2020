from django.urls import path
from . import views

app_name = "matches"

urlpatterns = [
    path("",                          views.matches_list,         name="list"),
    path("volunteer/<int:pk>/",       views.volunteer_detail,     name="volunteer_detail"),
    path("freemarket/<int:pk>/",      views.gift_offer_detail,    name="gift_offer_detail"),
    path("skills/<int:pk>/",          views.skill_interest_detail, name="skill_interest_detail"),
    path("action/<str:token>/",       views.email_action,         name="email_action"),
]
