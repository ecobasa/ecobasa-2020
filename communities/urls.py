from django.urls import path
from . import views

app_name = "communities"

urlpatterns = [
    path('', views.index, name='list'),
    path('create/', views.create, name='create'),
    path('<slug:slug>/edit/', views.update, name='update'),
    path('<slug:slug>/', views.detail, name='detail'),
]