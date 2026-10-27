"""Shared pieces for the dashboard's list pages (matches, references, messages): tabs
with counts, status filters and paging. Every list works the same way, so a page stays
short however much piles up over the years.

Views build the tabs and filters as `Choice`s and paginate with `paginate`; the
templates `dashboard/_tabs.html`, `_filters.html` and `_pager.html` draw them.
"""
from dataclasses import dataclass

from django.core.paginator import Paginator

PER_PAGE = 20


@dataclass
class Choice:
    """One tab or status filter: a link, how many items it holds, and how many of
    those wait for the viewer."""

    label: str
    url: str
    active: bool = False
    count: int | None = None
    waiting: int = 0
    icon: str = ""


def query_url(request, **params):
    """The current page's URL with some query parameters changed; None removes one.
    Switching tab or filter goes back to the first page."""
    query = request.GET.copy()
    query.pop("page", None)
    for key, value in params.items():
        if value is None:
            query.pop(key, None)
        else:
            query[key] = value
    return f"{request.path}?{query.urlencode()}" if query else request.path


def paginate(request, items, per_page=PER_PAGE):
    """A page of `items` (a list or queryset) for the `page` query parameter, with
    the links to the newer and older page kept on it for `dashboard/_pager.html`."""
    page = Paginator(items, per_page).get_page(request.GET.get("page"))
    page.newer_url = query_url(request, page=page.previous_page_number()) if page.has_previous() else None
    page.older_url = query_url(request, page=page.next_page_number()) if page.has_next() else None
    return page
