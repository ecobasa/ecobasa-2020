from django.urls import path

from . import views

app_name = "tours"

urlpatterns = [
    path("", views.tour_list, name="list"),
    path("new/", views.create, name="create"),
    path("api/hosts/", views.api_hosts, name="api-hosts"),
    path("api/routes/", views.api_routes, name="api-routes"),
    path("api/list/", views.api_list, name="api-list"),
    path("api/suggest/", views.api_suggest, name="api-suggest"),
    path("mine/", views.mine, name="mine"),
    path("<slug:slug>/", views.tour_detail, name="detail"),
    path("<slug:slug>/edit/", views.edit, name="edit"),
    path("<slug:slug>/plan/", views.plan, name="plan"),
    path("<slug:slug>/plan/stops/<int:pk>/edit/", views.stop_edit, name="stop_edit"),
    path("<slug:slug>/plan/stops/<int:pk>/move/<str:direction>/", views.stop_move, name="stop_move"),
    path("<slug:slug>/plan/stops/<int:pk>/delete/", views.stop_delete, name="stop_delete"),
    path("<slug:slug>/plan/learn/", views.learn_add, name="learn_add"),
    path("<slug:slug>/publish/", views.publish, name="publish"),
    path("<slug:slug>/archive/", views.archive, name="archive"),
    path("<slug:slug>/confirm/", views.confirm, name="confirm"),
    path("<slug:slug>/join/", views.join, name="join"),
    path("<slug:slug>/leave/", views.leave, name="leave"),
    path("<slug:slug>/travellers/<int:pk>/remove/", views.remove, name="remove"),
]
