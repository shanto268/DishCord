"""
Uses an LLM to parse a natural language user query into
a list of relevant ingredient strings. 
"""

import json
from typing import List

import requests


def parse_ingredients_with_llm(user_query: str, OLLAMA_URL: str, OLLAMA_MODEL: str) -> List[str]:
    """
    Calls the local GPT endpoint with a system prompt instructing it to
    extract ingredient words. 
    Returns a list of ingredient strings. If none found, returns empty list.
    """

    SYSTEM_PROMPT = """You are an ingredient extraction assistant. You receive a user’s question about cooking (e.g., “What can I make with cod?”). 
    Your task is to extract only the key ingredient words exactly as the user mentions them—no synonyms, no expansions, no interpretation beyond what’s literally provided. 

    Rules:
    1) Never add synonyms or guesses. For example, if the user says “cod,” do NOT add “fish.”
    2) If the user says “I want to make a dish with cod and garlic,” you return “cod, garlic.”
    3) Output the ingredients as a comma-separated list, with no extra text or explanation."""
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

def parse_query_with_llm(query: str, model_url: str, model_name: str) -> dict:
    """
    Uses the LLM to parse user queries intelligently.
    Example query: "!food show me 3 recipes for Italian food"
    Returns a structured dictionary with keys like:
    - action: "show", "find", etc.
    - filters: {"type": "Italian", "ingredients": ["shrimp", "garlic"]}
    - limit: 3
    """
    system_prompt = """
    You are an intelligent assistant that parses natural language food queries into actionable JSON.
    The user might ask for recipes by cuisine, difficulty, preparation time, or ingredients.
    Always respond with valid JSON that includes keys: "action", "filters", and "limit".

    Example Queries and Responses:
    Query: "Show me 3 Italian recipes"
    JSON: {"action": "show", "filters": {"type": "Italian"}, "limit": 3}

    Query: "Any quick and easy seafood recipes?"
    JSON: {"action": "find", "filters": {"difficulty": "easy", "type": "seafood"}, "limit": 5}

    Query: "Find recipes that use shrimp, garlic, and lemon"
    JSON: {"action": "find", "filters": {"ingredients": ["shrimp", "garlic", "lemon"]}, "limit": 5}

    Query: "Any suggestions for dinner?"
    JSON: {"action": "suggest", "filters": {}, "limit": 3}

    If the query is ambiguous, do your best to infer the user's intent based on common sense.
    """

    # Combine system prompt and user query
    prompt = f"{system_prompt}\n\nQuery: {query}\nJSON:"

    # Call the LLM
    payload = {"prompt": prompt, "model": model_name, "stream": False}
    try:
        response = requests.post(model_url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        parsed_response = data.get("response", "").strip()
        return json.loads(parsed_response)
    except Exception as e:
        print(f"[ERROR] LLM Query Parsing Failed: {e}")
        return {"action": "error", "filters": {}, "limit": 0}