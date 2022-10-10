# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections import namedtuple

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView


def fetch_one(cursor):
    """Return first row from a cursor as a namedtuple"""
    nt_result = namedtuple("SQLResult", [col[0] for col in cursor.description])
    row = cursor.fetchone()
    if row:
        return nt_result(*row)._asdict()
    else:
        return {}


def fetch_all(cursor):
    """Return all rows from a cursor as a namedtuple"""
    nt_result = namedtuple("SQLResult", [col[0] for col in cursor.description])
    return [nt_result(*row)._asdict() for row in cursor.fetchall()]


class Pagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "p_size"
    max_page_size = 1000
    page_query_param = "p"

    def get_paginated_response(self, results, additional_data):
        response_data = {
            "count": self.page.paginator.count,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "results": results,
        }
        response_data.update(additional_data)
        return Response(response_data)


class PaginatedApiView(APIView):
    ordering_fields = []
    search_fields = []
    default_order = None
    serializer_class = None
    model = None
    lookup_field = None
    queryset_extra = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.paginator = Pagination()
        ordering_fields = getattr(self, "ordering_fields", [])
        self.ordering_fields = []
        for field in ordering_fields:
            self.ordering_fields.append(field)
            self.ordering_fields.append("-{}".format(field))

        self.default_order = getattr(self, "default_order", None)

    def get_queryset(self, **kwargs):
        raise NotImplementedError

    def get_search_filters(self, request):
        search = request.query_params.get("search")
        filters = Q()
        if search:
            for field in self.search_fields:
                filters |= Q(**{"{}__icontains".format(field): search})
        return filters

    def get_ordering(self, request):
        param = request.query_params.get("order")
        if param in self.ordering_fields:
            return param
        return self.default_order

    def paginate_queryset(self, queryset):
        return self.paginator.paginate_queryset(queryset, self.request, view=self)

    def get_additional_data(self, queryset, **kwargs):
        return {}

    def get(self, request, **kwargs):
        if self.model:
            filter_kwargs = {self.lookup_field: kwargs[self.lookup_field]}
            obj = get_object_or_404(self.model, **filter_kwargs)
            if self.queryset_extra:
                for extra in self.queryset_extra:
                    kwargs[extra] = getattr(obj, extra)

        search_filters = self.get_search_filters(request)
        queryset = self.get_queryset(
            search_filters=search_filters, query_params=request.GET, **kwargs
        )
        order = self.get_ordering(request)
        if order:
            queryset = queryset.order_by(order)

        page = self.paginate_queryset(queryset)
        if page is not None:
            if self.serializer_class:
                serializer = self.serializer_class(page, many=True)
                page = serializer.data
            additional_data = self.get_additional_data(queryset, **kwargs)
            return self.paginator.get_paginated_response(page, additional_data)
        if self.serializer_class:
            serializer = self.serializer_class(queryset, many=True)
            queryset = serializer.data
        return Response(queryset)
