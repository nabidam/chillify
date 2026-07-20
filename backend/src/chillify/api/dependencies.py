"""Request-scoped dependency resolution.

Routes receive the composition root through FastAPI's dependency system so no
module reaches for a global binding, and tests can substitute a composition
built against disposable roots.
"""

from __future__ import annotations

from fastapi import Request

from chillify.composition import Composition


def get_composition(request: Request) -> Composition:
    composition: Composition = request.app.state.composition
    return composition
