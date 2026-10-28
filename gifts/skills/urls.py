from django.urls import path
from . import views

app_name = "skills"

urlpatterns = [
    path("",                  views.skill_list,            name="skill_list"),
    path("add/several/",      views.userskill_add_several, name="userskill_add_several"),
    path("api/autocomplete/", views.skill_autocomplete,    name="api_autocomplete"),
    path("api/proposals/",    views.skill_proposals,       name="api_proposals"),
    path("<slug:slug>/",      views.skill_detail,          name="skill_detail"),
]
