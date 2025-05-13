from collections import defaultdict
from src.models.message import Message
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CustomCache:
    def __init__(self):
        self.cache = defaultdict(list)
        self.cache["promotions"] = []
        self.cache["social"] = []

    def insert(self, category, messages):
        if category == "promotions":
            self.cache["promotions"].extend(messages)

        elif category == "social":
            self.cache["social"].extend(messages)

        else:
            logger.error(f"User entered the incorrect category type: {category}")
            raise ValueError(f"Invalid category: {category}")

    def get(self, category):
        return self.cache[category]

    def get_cache_data(self):
        return {
            "promotions": len(self.cache["promotions"]),
            "social": len(self.cache["social"]),
        }
