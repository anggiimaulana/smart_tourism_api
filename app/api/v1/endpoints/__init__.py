"""Endpoint modules for API v1.

TODO:
1. Keep each business area in its own endpoint module.
2. Put validation, HTTP handling, and dependency wiring here.
3. Delegate the actual work to service classes.
"""

from app.api.v1.endpoints import auth, chatbot, kuliner, nongkrong, recommendation, sentiment, wisata

__all__ = [
	"auth",
	"chatbot",
	"kuliner",
	"nongkrong",
	"recommendation",
	"sentiment",
	"wisata",
]