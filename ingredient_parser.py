"""
Uses an LLM to parse a natural language user query into
a list of relevant ingredient strings. 
"""

from typing import List

import requests

SYSTEM_PROMPT = """You are an ingredient extraction assistant. You receive a user’s question about cooking (e.g., “What can I make with cod?”). 
Your task is to extract only the key ingredient words exactly as the user mentions them—no synonyms, no expansions, no interpretation beyond what’s literally provided. 

Rules:
1) Never add synonyms or guesses. For example, if the user says “cod,” do NOT add “fish.”
2) If the user says “I want to make a dish with cod and garlic,” you return “cod, garlic.”
3) Output the ingredients as a comma-separated list, with no extra text or explanation."""

def parse_ingredients_with_llm(user_query: str, OLLAMA_URL: str, OLLAMA_MODEL: str) -> List[str]:
    """
    Calls the local GPT endpoint with a system prompt instructing it to
    extract ingredient words. 
    Returns a list of ingredient strings. If none found, returns empty list.
    """

    # You might do streaming or not; for simplicity let's do a single shot
    # Use a combined prompt approach:
    final_prompt = f"{SYSTEM_PROMPT}\nUser: {user_query}\nAssistant:"

    # Prepare request body (for /v1/completions style)
    payload = {
        "prompt": final_prompt,
        "model": OLLAMA_MODEL,  # example model, adapt as needed
        "stream": False
    }

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # data might be { "content": "...some text..." } or "response": ...
        # We'll assume "content" or "response" is returned. Adjust as needed.
        gpt_text = data.get("response", "").strip()  # or data.get("content", "")

        # Suppose GPT returns something like "shrimp, garlic, onion"
        # We parse it by splitting on commas
        if not gpt_text:
            return []

        raw_ingredients = [ing.strip() for ing in gpt_text.split(",") if ing.strip()]
        return raw_ingredients

    except Exception as e:
        print(f"[ERROR] parse_ingredients_with_gpt: {e}")
        return []