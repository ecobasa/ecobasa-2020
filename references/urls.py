from django.urls import path
from . import views

app_name = "references"

# delete/ first: "<int>/delete/" would otherwise match the save pattern.
urlpatterns = [
    path("",                                       views.references_list, name="list"),
    path("<int:pk>/delete/",                       views.delete, name="delete"),
    path("skill/<int:pk>/<str:action>/",           views.skill_tag, name="skill_tag"),
    path("request/<str:key>/",                     views.reference_request, name="request"),
    path("featured/",                              views.featured, name="featured"),
    path("<int:content_type_id>/<str:object_id>/", views.save,   name="save"),
]
