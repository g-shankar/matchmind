"""One error type for everything the ingest adapter refuses."""

from __future__ import annotations

from pydantic import ValidationError

MAX_PROBLEMS = 10


class IngestError(ValueError):
    """A feed, roster or mapping the adapter will not play. The message is plain words;
    `problems` lists up to MAX_PROBLEMS specific reasons (with line numbers when known)."""

    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        self.problems = list(problems or [])[:MAX_PROBLEMS]
        detail = message if not self.problems else f"{message}: " + "; ".join(self.problems)
        super().__init__(detail)
        self.summary = message

    @classmethod
    def from_validation(cls, what: str, exc: ValidationError, where: str = "") -> IngestError:
        problems = []
        for err in exc.errors()[:MAX_PROBLEMS]:
            loc = ".".join(str(p) for p in err.get("loc", ()))
            msg = str(err.get("msg", "invalid")).removeprefix("Value error, ")
            problems.append(f"{where}{loc}: {msg}" if loc else f"{where}{msg}")
        return cls(f"The {what} is not valid", problems)
