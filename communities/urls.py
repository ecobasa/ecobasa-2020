from django.urls import path
from . import views

app_name = "communities"

urlpatterns = [
    path('', views.index, name='list'),
    path('create/', views.create, name='create'),
    path('<slug:slug>/edit/', views.update, name='update'),
    path('<slug:slug>/delete/', views.delete, name='delete'),
    path('<slug:slug>/', views.detail, name='detail'),
    # API endpoints for the map template
    path('api/markers/', views.community_markers, name='api-markers'),
    path('api/list/', views.community_list_partial, name='api-list'),
    path('api/suggest/', views.community_suggest, name='api-suggest'),
]
