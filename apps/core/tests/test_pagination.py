from rest_framework.generics import ListAPIView
from rest_framework.serializers import IntegerField, Serializer
from rest_framework.test import APIRequestFactory

from apps.core.api.pagination import PageNumberPagination


class _NumberSerializer(Serializer):
    value = IntegerField()


class _NumberListView(ListAPIView):
    authentication_classes = []
    permission_classes = []
    serializer_class = _NumberSerializer
    pagination_class = PageNumberPagination

    def get_queryset(self):
        return [{"value": n} for n in range(1, 26)]


def test_paginated_response_shape_and_default_page_size():
    request = APIRequestFactory().get("/x/")

    response = _NumberListView.as_view()(request)

    assert response.status_code == 200
    assert response.data["count"] == 25
    assert len(response.data["results"]) == 20


def test_page_size_query_param_is_honoured_up_to_the_max():
    request = APIRequestFactory().get("/x/?page_size=5")

    response = _NumberListView.as_view()(request)

    assert len(response.data["results"]) == 5


def test_page_size_query_param_is_capped_at_the_max():
    request = APIRequestFactory().get("/x/?page_size=1000")

    response = _NumberListView.as_view()(request)

    assert len(response.data["results"]) == 25
