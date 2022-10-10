# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import collections
import itertools

import serpy

from maker.utils.views import PaginatedApiView

from ..models import ForumPost


class ForumPostSerializer(serpy.DictSerializer):
    segments = serpy.Field()
    vault_types = serpy.Field()
    title = serpy.StrField()
    description = serpy.StrField()
    url = serpy.StrField()
    publish_date = serpy.Field()
    publisher = serpy.StrField()


class ForumArchiveView(PaginatedApiView):
    serializer_class = ForumPostSerializer
    default_order = "-publish_date"

    def get_additional_data(self, queryset, **kwargs):
        segment_arrays = (
            ForumPost.objects.all()
            .values_list("segments", flat=True)
            .order_by("-publish_date")
        )
        segments = itertools.chain.from_iterable(
            array for array in segment_arrays if array
        )
        segment_counts = collections.Counter(segments)
        segment_data = [
            {"title": title, "count": count}
            for title, count in segment_counts.most_common()
        ]
        return {"segments": segment_data}

    def get_queryset(self, search_filters, **kwargs):
        segment = self.request.GET.get("category")
        if segment:
            posts = ForumPost.objects.filter(segments__contains=[segment]).values()
        else:
            posts = ForumPost.objects.all().values()
        return posts
