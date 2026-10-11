"""Settings that control how map content is rendered, scoped to the current render run."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, fields
from typing import Any

from mapbuilder import MapbuilderException


@dataclass(frozen=True, slots=True)
class RenderContext:
    """Render settings, configured in the ``[render]`` section of mapbuilder.toml."""

    # Decimal places of coordinates; None keeps Python's full float representation
    precision: int | None = None

    def __post_init__(self) -> None:
        precision = self.precision
        if precision is not None and (isinstance(precision, bool) or not isinstance(precision, int)
                                      or not 0 <= precision <= 15):
            msg = f"render.precision must be an integer between 0 and 15, not {precision!r}"
            raise MapbuilderException(msg)

    @classmethod
    def from_config(cls, settings: Mapping[str, Any]) -> "RenderContext":
        """Creates a context from the ``[render]`` section, rejecting unknown settings."""
        unknown = settings.keys() - {f.name for f in fields(cls)}
        if unknown:
            msg = f"Unknown render setting(s): {', '.join(sorted(unknown))}"
            raise MapbuilderException(msg)

        return cls(**settings)

    @property
    def cache_key(self) -> str:
        """Identifies the settings in cache keys of rendered content."""
        return f"precision={self.precision}"


_DEFAULT = RenderContext()
_current: ContextVar[RenderContext | None] = ContextVar("render_context", default=None)


def current_render_context() -> RenderContext:
    """The render context of the current run (defaults if none is active)."""
    return _current.get() or _DEFAULT


@contextmanager
def use_render_context(context: RenderContext) -> Iterator[RenderContext]:
    """Activates a render context for the enclosed rendering; restores the previous one afterwards."""
    token = _current.set(context)
    try:
        yield context
    finally:
        _current.reset(token)
