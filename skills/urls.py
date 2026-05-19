from django.urls import path
from . import views

app_name = "skills"

urlpatterns = [
    path("",                                                          views.skill_list,              name="skill_list"),
    path("add/",                                                      views.userskill_add,           name="userskill_add"),
    path("api/autocomplete/",                                         views.skill_autocomplete,      name="api_autocomplete"),
    path("community/<slug:community_slug>/add/",                      views.communityskill_add,      name="communityskill_add"),
    path("wish/user/<str:user_slug>/<slug:skill_slug>/",              views.skillwish_user_detail,   name="skillwish_user_detail"),
    path("wish/<int:pk>/edit/",                                       views.skillwish_user_edit,     name="skillwish_user_edit"),
    path("wish/<int:pk>/community/<slug:community_slug>/edit/",       views.skillwish_community_edit, name="skillwish_community_edit"),

    path("<slug:slug>/",                                              views.skill_detail,            name="skill_detail"),
    path("<slug:skill_slug>/user/<str:user_slug>/",                   views.userskill_detail,        name="userskill_detail"),
    path("<slug:skill_slug>/user/<str:user_slug>/edit/",              views.userskill_edit,          name="userskill_edit"),
    path("<slug:skill_slug>/user/<str:user_slug>/delete/",            views.userskill_delete,        name="userskill_delete"),
    path("<slug:skill_slug>/community/<slug:community_slug>/",        views.communityskill_detail,   name="communityskill_detail"),
    path("<slug:skill_slug>/community/<slug:community_slug>/edit/",   views.communityskill_edit,     name="communityskill_edit"),
    path("<slug:skill_slug>/community/<slug:community_slug>/delete/", views.communityskill_delete,   name="communityskill_delete"),
]
