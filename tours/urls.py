from django.urls import path

from . import views

app_name = "tours"

urlpatterns = [
    path("", views.tour_list, name="list"),
    path("new/", views.create, name="create"),
    path("api/hosts/", views.api_hosts, name="api-hosts"),
    path("<slug:slug>/", views.tour_detail, name="detail"),
    path("<slug:slug>/edit/", views.edit, name="edit"),
    path("<slug:slug>/stops/", views.stops, name="stops"),
    path("<slug:slug>/stops/<int:pk>/edit/", views.stop_edit, name="stop_edit"),
    path("<slug:slug>/stops/<int:pk>/move/<str:direction>/", views.stop_move, name="stop_move"),
    path("<slug:slug>/stops/<int:pk>/delete/", views.stop_delete, name="stop_delete"),
    path("<slug:slug>/publish/", views.publish, name="publish"),
    path("<slug:slug>/archive/", views.archive, name="archive"),
    path("<slug:slug>/confirm/", views.confirm, name="confirm"),
]
