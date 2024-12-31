# bot.py
import json
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

from models.recipe import Recipe

load_dotenv("../.env")

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN") 
OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

SYSTEM_PROMPT = """You are a concise, knowledgeable assistant. 
Give brief yet helpful answers, usually 1–5 sentences. 
Include enough detail to address the question thoroughly, 
but do not ramble or include irrelevant commentary or disclaimers. 
If there's prior context in the conversation, use it as needed.
"""

class MemoryManager:
    def __init__(self, max_history=5):
        # store dict: { channel_id: [(role, message), ...], ... }
        self.conversation_history = {}
        self.max_history = max_history
    
    def add_message(self, channel_id, role, content):
        """
        Add a message to the channel's conversation log.
        Trim older messages if we exceed self.max_history.
        """
        if channel_id not in self.conversation_history:
            self.conversation_history[channel_id] = []
        self.conversation_history[channel_id].append((role, content))
        # Trim if we exceed max
        if len(self.conversation_history[channel_id]) > self.max_history:
            self.conversation_history[channel_id].pop(0)

    def build_prompt(self, channel_id):
        """
        Build final prompt from system instructions + conversation history + "Assistant:".
        """
        lines = [f"System: {SYSTEM_PROMPT}"]
        # add messages from memory
        if channel_id in self.conversation_history:
            for (role, text) in self.conversation_history[channel_id]:
                lines.append(f"{role}: {text}")
        # final line: assistant responds
        lines.append("Assistant:")
        return "\n".join(lines)

    def summarize_context(self, channel_id):
        """
        Returns a short listing of what user asked and what the assistant replied.
        Example format for each stored pair:
          Q: <user text>
          A: <assistant text>
        """
        if channel_id not in self.conversation_history or not self.conversation_history[channel_id]:
            return "No previous context in this channel."

        # Gather pairs of (User, Assistant) messages
        user_idx = 1
        summary_lines = []
        user_buffer = None

        for (role, text) in self.conversation_history[channel_id]:
            if role == "User":
                user_buffer = text
            elif role == "Assistant" and user_buffer:
                summary_lines.append(f"Q{user_idx}: {user_buffer}\nA{user_idx}: {text}")
                user_buffer = None
                user_idx += 1

        # if there's a user msg at the end without an assistant reply, handle it
        if user_buffer is not None:
            summary_lines.append(f"Q{user_idx}: {user_buffer}\nA{user_idx}: *(No assistant reply yet)*")

        if not summary_lines:
            return "No user Q&A found yet."

        return "\n\n".join(summary_lines)

class RecipeManager:
    """
    Stores a list of Recipe objects and provides methods for loading
    and searching them by ingredients.
    """

    def __init__(self):
        self.recipes = []

    def load_from_json(self, json_path: str) -> None:
        """
        Loads recipes from a JSON file (the structure shown in your example).
        """
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"Recipe JSON file not found at {json_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("Expected a list of recipe records in JSON.")

            for record in data:
                pinterest_url = record.get("pinterest_url", "")
                source_url = record.get("source_url", "")
                recipe_data = record.get("recipe_data", {})
                title = recipe_data.get("title", "")
                image_url = recipe_data.get("image_url", "")
                ingredients = recipe_data.get("ingredients", [])

                recipe_obj = Recipe(
                    pinterest_url=pinterest_url,
                    source_url=source_url,
                    title=title,
                    image_url=image_url,
                    ingredients=ingredients
                )
                self.recipes.append(recipe_obj)

    def find_recipes_by_ingredients(self, user_ingredients: List[str]) -> List[Recipe]:
        """
        Returns a list of recipes that match the given user_ingredients.
        """
        if not user_ingredients:
            return []

        matched = []
        for recipe in self.recipes:
            # recipe.fetch_title_from_pinterest()
            if recipe.has_ingredients(user_ingredients):
                matched.append(recipe)
        return matched