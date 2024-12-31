import json
import os

import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv("../.env")

OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")


def parse_llm_response(response_text):
    """
    Parses the LLM response text to extract JSON-like data.
    Strips extra explanations or text outside the JSON block.
    """
    try:
        start_idx = response_text.find("{")
        end_idx = response_text.rfind("}")
        if start_idx == -1 or end_idx == -1:
            raise ValueError("JSON block not found in response text.")
        json_block = response_text[start_idx:end_idx + 1]
        return json.loads(json_block)
    except Exception as e:
        print(f"Error parsing response text: {e}")
        return {"cuisines": [], "difficulty": "unknown", "time": "unknown"}


def analyze_recipe_with_llm(title, ingredients, model_url, model_name):
    """
    Uses a local LLM (OLLAMA_MODEL) to classify cuisine, difficulty, and estimate time.
    :param title: The title of the recipe.
    :param ingredients: List of ingredients.
    :param model_url: URL of the Ollama model endpoint.
    :param model_name: Name of the Ollama model.
    :return: A dictionary with cuisine tags, difficulty, and estimated time.
    """
    prompt = (
        "You are an expert culinary assistant. Analyze recipes based on their title and ingredients. "
        "Provide the following details:\n"
        "1. Cuisine tags: A list of possible cuisines like 'Italian', 'Mexican', 'Sichuan', 'American', "
        "'Mediterranean', 'French', 'Indian', 'Seafood', 'Thai', 'Noodles', 'Breakfast', 'Lunch', etc.\n"
        "2. Difficulty: Either 'easy', 'medium', or 'tough', depending on how complex it is to make the dish.\n"
        "3. Estimated time: A reasonable estimate of the total time required to prepare the dish, in the format "
        "'{number} {unit}' where number can be a float, and unit is either 'minutes' or 'hours'.\n\n"
        f"Title: {title}\n"
        f"Ingredients: {', '.join(ingredients) if ingredients else 'No ingredients provided'}\n"
        "Output the details in the following JSON format:\n"
        "{\n"
        "  \"cuisines\": [\"cuisine1\", \"cuisine2\", ...],\n"
        "  \"difficulty\": \"easy|medium|tough\",\n"
        "  \"time\": \"{number} {unit}\"\n"
        "}\n"
    )

    payload = {
        "prompt": prompt,
        "model": model_name,
        "stream": False
    }

    try:
        response = requests.post(model_url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        response_text = data.get("response", "").strip()
        return parse_llm_response(response_text)
    except requests.exceptions.RequestException as e:
        print(f"Error making request to Ollama for title '{title}': {e}")
        return {"cuisines": [], "difficulty": "unknown", "time": "unknown"}
    except Exception as e:
        print(f"Unexpected error for title '{title}': {e}")
        return {"cuisines": [], "difficulty": "unknown", "time": "unknown"}


def add_analysis_tags_with_llm(input_file, output_file):
    """
    Reads a JSON file, uses the LLM to classify cuisines, difficulty, and time for each recipe,
    and writes the updated data back to a new file.
    :param input_file: Path to the input JSON file.
    :param output_file: Path to the output JSON file.
    """
    # Load recipes
    with open(input_file, "r", encoding="utf-8") as f:
        recipes = json.load(f)

    # Analyze recipes and update
    for recipe in recipes:
        title = recipe["recipe_data"].get("title", "")
        ingredients = recipe["recipe_data"].get("ingredients", [])
        print(f"Analyzing recipe: {title}")

        analysis = analyze_recipe_with_llm(title, ingredients, OLLAMA_URL, OLLAMA_MODEL)

        # Update the recipe with the analysis results
        recipe["recipe_data"]["extra"]["cuisines"] = analysis.get("cuisines", [])
        recipe["recipe_data"]["extra"]["difficulty"] = analysis.get("difficulty", "unknown")
        recipe["recipe_data"]["extra"]["time"] = analysis.get("time", "unknown")

    # Write updated recipes to output file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(recipes, f, indent=2, ensure_ascii=False)

    print(f"Updated recipes with analysis tags saved to {output_file}")


if __name__ == "__main__":
    # Input and output file paths
    input_file = "recipes_all.json"
    output_file = "recipes_all_analyzed.json"

    # Add analysis tags using the LLM
    add_analysis_tags_with_llm(input_file, output_file)