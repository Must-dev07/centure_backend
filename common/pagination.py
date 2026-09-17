from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """Bounded pagination on every list endpoint — no unbounded queries."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500
