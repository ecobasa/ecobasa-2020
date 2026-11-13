from django.shortcuts import redirect, render
from django.utils.translation import pgettext


def index(request):
    return render(request, "help/index.html")


def tours(request):
    return render(request, "help/tours.html")


def travelling_tips(request):
    return render(request, "help/travelling_tips.html")


def other_language(request, rest):
    """/help/ and /hilfe/ are the same pages: the spelling of another language leads to
    the one of the page's language (a shared link, or the language switched)."""
    url = "/" + pgettext("url", "help/") + rest
    if request.META.get("QUERY_STRING"):
        url += "?" + request.META["QUERY_STRING"]
    return redirect(url)
