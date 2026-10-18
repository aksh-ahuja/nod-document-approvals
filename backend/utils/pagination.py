from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .helpers import get_success_response


class NodPagination(PageNumberPagination):
    page_size = 12

    def get_paginated_response(self, data):
        return Response(
            get_success_response(
                {
                    'results': data,
                    'count': self.page.paginator.count,
                    'page': self.page.number,
                    'pages': self.page.paginator.num_pages,
                }
            )
        )
