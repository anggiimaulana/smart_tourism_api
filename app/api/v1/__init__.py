"""Versioned API package.

TODO:
1. Keep v1 route aggregation in this package.
2. Add new version routers here when the API evolves.
"""

from app.api.v1.router import router

__all__ = ["router"]