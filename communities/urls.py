from django.urls import path
from . import views

app_name = "communities"

urlpatterns = [
    path('', views.index, name='list'),
    path('create/', views.create, name='create'),
    path('<slug:slug>/edit/', views.update, name='update'),
    path('<slug:slug>/delete/', views.delete, name='delete'),
    path('<slug:slug>/', views.detail, name='detail'),
    path('<slug:slug>/members/apply/', views.apply, name='apply'),
    path('<slug:slug>/members/leave/', views.leave, name='leave'),
    path('<slug:slug>/members/<int:pk>/remove/', views.remove_member, name='remove_member'),
    path('<slug:slug>/members/<int:pk>/ambassador/', views.hand_over, name='hand_over'),
    path('volunteer-request/<slug:community_slug>/', views.volunteer_request, name='volunteer_request'),
    # API endpoints for the map template
    path('api/markers/', views.community_markers, name='api-markers'),
    path('api/list/', views.community_list_partial, name='api-list'),
    path('api/suggest/', views.community_suggest, name='api-suggest'),
]
