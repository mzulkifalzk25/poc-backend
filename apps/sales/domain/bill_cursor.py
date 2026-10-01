import base64
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class BillCursor:
    """Keyset position for the newest-first bill list: `(sold_at, id)`."""

    sold_at: datetime
    id: UUID

    def encode(self) -> str:
        raw = f"{self.sold_at.isoformat()}|{self.id}"
        return base64.urlsafe_b64encode(raw.encode()).decode()

    @classmethod
    def decode(cls, token: str) -> BillCursor:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        sold_at_text, id_text = raw.rsplit("|", 1)
        return cls(sold_at=datetime.fromisoformat(sold_at_text), id=UUID(id_text))
