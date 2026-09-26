from rest_framework import serializers

from apps.core.domain.cursor import Cursor

MAX_SYNC_PAGE = 2000


class SyncQuerySerializer(serializers.Serializer):
    """`since` is `0` (or missing) for a full sync, else the previous
    `next_since`, sent back unchanged."""

    since = serializers.CharField(required=False, allow_blank=True)
    page_size = serializers.IntegerField(
        required=False, min_value=1, max_value=MAX_SYNC_PAGE, default=MAX_SYNC_PAGE
    )

    def validate_since(self, value: str) -> Cursor | None:
        if value in ("", "0"):
            return None
        try:
            return Cursor.decode(value)
        except ValueError:
            raise serializers.ValidationError("Not a sync cursor from this server.") from None
