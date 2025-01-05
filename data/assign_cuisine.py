import asyncio
import json
import os
from typing import Dict, List

import aiohttp
from aiohttp import ClientSession
from dotenv import load_dotenv
from tqdm.asyncio import tqdm_asyncio

# Load environment variables from .env file
load_dotenv("../.env")

OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")
MAX_RETRIES = 3  # Number of retries for failed requests


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
        "}\n")

    payload = {"prompt": prompt, "model": model_name, "stream": False}

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
        try:
            title = recipe["recipe_data"].get("title", "")
            ingredients = recipe["recipe_data"].get("ingredients", [])
            print(f"Analyzing recipe: {title}")

            # Ensure "extra" field exists
            recipe["recipe_data"].setdefault("extra", {})

            # Analyze the recipe using LLM
            analysis = analyze_recipe_with_llm(title, ingredients, OLLAMA_URL,
                                               OLLAMA_MODEL)

            # Populate analysis results
            recipe["recipe_data"]["extra"]["cuisines"] = analysis.get(
                "cuisines", [])
            recipe["recipe_data"]["extra"]["difficulty"] = analysis.get(
                "difficulty", "unknown")
            recipe["recipe_data"]["extra"]["time"] = analysis.get(
                "time", "unknown")

        except KeyError as ke:
            print(f"KeyError for recipe: {title} - {ke}")
            with open("error_log.txt", "a") as error_file:
                error_file.write(f"KeyError for recipe: {title} - {ke}\n")
                error_file.write(f"Recipe: {json.dumps(recipe, indent=2)}\n")

        except Exception as e:
            print(f"Error analyzing recipe for title '{title}': {e}")
            with open("error_log.txt", "a") as error_file:
                error_file.write(
                    f"Error analyzing recipe for title '{title}': {e}\n")
                error_file.write(f"Recipe: {json.dumps(recipe, indent=2)}\n")

            # Fallback for failed analysis
            recipe["recipe_data"]["extra"]["cuisines"] = []
            recipe["recipe_data"]["extra"]["difficulty"] = "unknown"
            recipe["recipe_data"]["extra"]["time"] = "unknown"

    # Write updated recipes to output file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(recipes, f, indent=2, ensure_ascii=False)

    print(f"Updated recipes with analysis tags saved to {output_file}")



def analyze_recipe(recipe: Dict) -> Dict:
    """
    Wrapper to analyze a single recipe and update its data.
    """
    title = recipe["recipe_data"].get("title", "")
    ingredients = recipe["recipe_data"].get("ingredients", [])
    print(f"Process {os.getpid()} analyzing recipe: {title}")

    analysis = analyze_recipe_with_llm(title, ingredients, OLLAMA_URL, OLLAMA_MODEL)

    # Update the recipe with the analysis results
    if "extra" not in recipe["recipe_data"]:
        recipe["recipe_data"]["extra"] = {}
    recipe["recipe_data"]["extra"]["cuisines"] = analysis.get("cuisines", [])
    recipe["recipe_data"]["extra"]["difficulty"] = analysis.get("difficulty", "unknown")
    recipe["recipe_data"]["extra"]["time"] = analysis.get("time", "unknown")

    return recipe


def add_analysis_tags_with_multiprocessing(input_file: str, output_file: str, num_workers: int = 4):
    """
    Processes recipes in parallel using multiprocessing.Pool.
    Handles IO-bound tasks by allowing more workers than cores.
    """
    # Load recipes
    with open(input_file, "r", encoding="utf-8") as f:
        recipes = json.load(f)

    print(f"Processing {len(recipes)} recipes using {num_workers} workers.")

    # Process recipes in parallel with a progress bar
    with Pool(num_workers) as pool:
        with tqdm(total=len(recipes), desc="Processing Recipes", unit="recipe") as pbar:
            updated_recipes = []
            for recipe in pool.imap_unordered(analyze_recipe, recipes):
                updated_recipes.append(recipe)
                pbar.update()

    # Write updated recipes to output file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(updated_recipes, f, indent=2, ensure_ascii=False)

    print(f"Updated recipes with analysis tags saved to {output_file}")

async def analyze_recipe_with_llm_async(session, title, ingredients, model_url, model_name, semaphore):
    """
    Asynchronously analyzes a single recipe using the LLM API with retries and rate limiting.
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
        "}\n")

    payload = {"prompt": prompt, "model": model_name, "stream": False}

    retries = 0
    while retries < MAX_RETRIES:
        try:
            async with semaphore:
                async with session.post(model_url, json=payload, timeout=30) as response:
                    if response.status != 200:
                        print(f"Error {response.status} for title '{title}': {await response.text()}")
                        raise aiohttp.ClientError(f"Status code: {response.status}")

                    data = await response.json()
                    response_text = data.get("response", "").strip()
                    return parse_llm_response(response_text)

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            retries += 1
            print(f"Retry {retries}/{MAX_RETRIES} for title '{title}' due to: {e}")

    # Fallback after retries
    print(f"Failed to analyze recipe '{title}' after {MAX_RETRIES} retries.")
    return {"cuisines": [], "difficulty": "unknown", "time": "unknown"}


async def analyze_recipe_async(recipe, session, semaphore):
    """
    Analyzes a single recipe asynchronously and updates its "extra" field.
    """
    title = recipe["recipe_data"].get("title", "")
    ingredients = recipe["recipe_data"].get("ingredients", [])
    print(f"Analyzing recipe: {title}")

    analysis = await analyze_recipe_with_llm_async(session, title, ingredients, OLLAMA_URL, OLLAMA_MODEL, semaphore)

    if "extra" not in recipe["recipe_data"]:
        recipe["recipe_data"]["extra"] = {}

    recipe["recipe_data"]["extra"]["cuisines"] = analysis.get("cuisines", [])
    recipe["recipe_data"]["extra"]["difficulty"] = analysis.get("difficulty", "unknown")
    recipe["recipe_data"]["extra"]["time"] = analysis.get("time", "unknown")

    return recipe


async def add_analysis_tags_with_asyncio(input_file: str, output_file: str, max_concurrent: int = 10):
    """
    Processes recipes concurrently using asyncio and aiohttp with rate limiting and retries.
    """
    # Load recipes
    with open(input_file, "r", encoding="utf-8") as f:
        recipes = json.load(f)

    print(f"Processing {len(recipes)} recipes using {max_concurrent} concurrent tasks.")

    semaphore = asyncio.Semaphore(max_concurrent)  # Limit concurrency
    async with aiohttp.ClientSession() as session:
        tasks = [
            analyze_recipe_async(recipe, session, semaphore)
            for recipe in recipes
        ]

        # Use tqdm for progress bar
        updated_recipes = []
        for coro in tqdm_asyncio.as_completed(tasks, desc="Processing Recipes", total=len(recipes)):
            updated_recipes.append(await coro)

    # Write updated recipes to output file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(updated_recipes, f, indent=2, ensure_ascii=False)

    print(f"Updated recipes with analysis tags saved to {output_file}")


if __name__ == "__main__":
    # Input and output file paths
    input_file = "recipes_all.json"
    output_file = "recipes_all_analyzed.json"

    # Add analysis tags using asyncio
    asyncio.run(add_analysis_tags_with_asyncio(input_file, output_file, max_concurrent=4))
    # Add analysis tags using the LLM
    # add_analysis_tags_with_llm(input_file, output_file)
    # add_analysis_tags_with_multiprocessing(input_file, output_file, num_workers=8)