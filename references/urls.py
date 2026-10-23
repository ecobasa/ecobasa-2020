from django.urls import path
from . import views

app_name = "references"

# delete/ first: "<int>/delete/" would otherwise match the save pattern.
urlpatterns = [
    path("<int:pk>/delete/",                       views.delete, name="delete"),
    path("<int:content_type_id>/<str:object_id>/", views.save,   name="save"),
]
