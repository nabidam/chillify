"""Shared wire envelopes.

The success envelope for every collection is `{"items": [], "next_cursor": null}`
so a client's paging code is written once and reused everywhere.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageModel[Item](BaseModel):
    """One keyset page of resources."""

    items: list[Item]
    next_cursor: str | None = Field(
        default=None,
        description="Opaque cursor for the next page, or null when this page is the last.",
    )
