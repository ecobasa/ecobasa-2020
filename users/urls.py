from django.urls import path
from . import views

app_name = "users"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.logout, name="logout"),
    path("register/", views.register, name="register"),
    path("edit/", views.UpdateView.as_view(), name="update"),
    # password reset:
    path("password_reset/", views.PasswordResetView.as_view(), name="password_reset",),
    path(
        "password_reset/done/",
        views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
        path("autocomplete/", views.autocomplete, name="autocomplete"),
    path("dismiss-skill-nudge/", views.dismiss_skill_nudge, name="dismiss_skill_nudge"),
        path("<slug>/", views.DetailView.as_view(), name="detail"),
]
