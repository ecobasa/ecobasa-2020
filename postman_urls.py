from django.urls import path
import postman.urls as _postman_urls

from postman_wrappers import message_view_wrapper

# Prepend our wrapper for the message detail view, then include the original postman urlpatterns.
urlpatterns = [
    path("view/<int:message_id>/", message_view_wrapper, name="view"),
] + getattr(_postman_urls, "urlpatterns", [])
