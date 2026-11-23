from django.urls import path
from . import views

app_name = "users"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.logout, name="logout"),
    path("register/", views.register, name="register"),
    path("edit/", views.UpdateView.as_view(), name="update"),
    path("email/<token>/", views.confirm_email, name="confirm_email"),
    path("confirm/", views.resend_confirmation, name="resend_confirmation"),
    path("confirm/<token>/", views.confirm_signup, name="confirm_signup"),
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
    path("<slug>/", views.DetailView.as_view(), name="detail"),
]
