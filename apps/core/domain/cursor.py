import base64
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Cursor:
    """An opaque keyset-paging position: the last row's ordering key and id."""

    occurred_at: datetime
    id: int

    def encode(self) -> str:
        raw = f"{self.occurred_at.isoformat()}|{self.id}"
        return base64.urlsafe_b64encode(raw.encode()).decode()

    @classmethod
    def decode(cls, token: str) -> Cursor:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        occurred_at_text, id_text = raw.rsplit("|", 1)
        return cls(occurred_at=datetime.fromisoformat(occurred_at_text), id=int(id_text))
