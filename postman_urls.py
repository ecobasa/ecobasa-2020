from django.urls import path
import postman.urls as _postman_urls

import postman_wrappers
from postman_wrappers import message_view_wrapper

# Prepend our wrapper for the message detail view, then include the original postman urlpatterns.
urlpatterns = [
    path("view/<int:message_id>/", message_view_wrapper, name="view"),
    # intercept write routes so we can append sender skills server-side
    path("write/", postman_wrappers.postman_write_wrapper, name="write"),
    path("write/<path:recipients>/", postman_wrappers.postman_write_wrapper, name="write_with_recipients"),
] + getattr(_postman_urls, "urlpatterns", [])
