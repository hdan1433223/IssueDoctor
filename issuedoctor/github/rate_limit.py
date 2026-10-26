from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class RateLimit:
    limit: int | None = None
    remaining: int | None = None
    reset: int | None = None

    @classmethod
    def from_headers(cls, headers: httpx.Headers) -> "RateLimit":
        def integer(name: str) -> int | None:
            value = headers.get(name)
            return int(value) if value and value.isdigit() else None

        return cls(
            limit=integer("X-RateLimit-Limit"),
            remaining=integer("X-RateLimit-Remaining"),
            reset=integer("X-RateLimit-Reset"),
        )

    def as_dict(self) -> dict[str, int | None]:
        return {"limit": self.limit, "remaining": self.remaining, "reset": self.reset}

