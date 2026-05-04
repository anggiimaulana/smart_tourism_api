"""Core application primitives.

TODO:
1. Keep shared app configuration here.
2. Import database and security helpers from this package when wiring endpoints.
3. Add new cross-cutting utilities only if they are reused across multiple modules.
"""

from app.core.config import Settings, settings
from app.core.database import AsyncSessionLocal, Base, engine, get_db
from app.core.security import (
	bearer_scheme,
	create_access_token,
	get_current_user,
	get_current_user_optional,
	hash_password,
	require_admin,
	verify_password,
)

__all__ = [
	"AsyncSessionLocal",
	"Base",
	"Settings",
	"bearer_scheme",
	"create_access_token",
	"engine",
	"get_current_user",
	"get_current_user_optional",
	"get_db",
	"hash_password",
	"require_admin",
	"settings",
	"verify_password",
]