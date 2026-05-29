"""ORM model exports.

TODO:
1. Import every table model here so SQLAlchemy metadata is registered on startup.
2. Keep one model per file to make migrations and maintenance easier.
3. Add new models to this file as soon as they are introduced.
"""

from app.models.chatbot_session import ChatbotSession
from app.models.chatbot_cache import ChatbotCache
from app.models.kuliner import Kuliner
from app.models.nongkrong import Nongkrong
from app.models.planning_wisata import PlanningWisata
from app.models.sentiment_result import SentimentResult
from app.models.user import User
from app.models.user_history import UserHistory
from app.models.user_preference import UserPreference
from app.models.wisata import Wisata
 
__all__ = [
    "ChatbotSession",
    "ChatbotCache",
    "Kuliner",
    "Nongkrong",
    "PlanningWisata",
    "SentimentResult",
    "User",
    "UserHistory",
    "UserPreference",
    "Wisata",
]