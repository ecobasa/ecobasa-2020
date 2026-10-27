from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("new/<slug:community_slug>/", views.create, name="create"),
    path("confirm/<str:token>/", views.confirm_by_email, name="confirm_by_email"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/edit/", views.edit, name="edit"),
    path("<int:pk>/archive/", views.archive, name="archive"),
    path("<int:pk>/confirm/", views.confirm, name="confirm"),
    path("<int:pk>/help/", views.offer_help, name="offer_help"),
    path("<int:pk>/needs/<int:need_pk>/toggle/", views.toggle_need, name="toggle_need"),
]
