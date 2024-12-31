"""
models/recipe.py

Defines the Recipe class to store recipe data and a helper method
to check ingredient matching.
"""

from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from rapidfuzz import fuzz


def fuzzy_match_ingredient(user_ing: str, recipe_ingredient: str) -> bool:
    ratio = fuzz.partial_ratio(user_ing.lower(), recipe_ingredient.lower())
    return ratio >= 90  # or tweak threshold

def has_ingredients_fuzzy(recipe_ingredients, user_ingredients):
    for ui in user_ingredients:
        matched = any(fuzzy_match_ingredient(ui, ri) for ri in recipe_ingredients)
        if not matched:
            return False
    return True

class Recipe:
    """
    Represents a single recipe, including title, image URL, ingredients,
    and the source URL for the recipe.
    """

    def __init__(
        self,
        pinterest_url: str,
        source_url: str,
        title: str,
        image_url: str,
        ingredients: Optional[List[str]] = None,
        extra: Optional[dict] = None
    ):
        self.pinterest_url = pinterest_url
        self.source_url = source_url
        self.title = title 
        self.image_url = image_url
        self.ingredients = ingredients if ingredients else []
        self.extra = extra

    def has_ingredients_v0(self, user_ingredients: List[str]) -> bool:
        """
        Returns True if *all* the user's ingredients appear in this recipe's
        ingredient list (case-insensitive substring matching).
        """
        recipe_ings_lower = [ing.lower() for ing in self.ingredients]

        for user_ing in user_ingredients:
            user_ing_lower = user_ing.strip().lower()
            # If user_ing_lower not found as a substring in ANY recipe ingredient,
            # we say this recipe doesn't match.
            found_in_this_recipe = any(user_ing_lower in r_ing for r_ing in recipe_ings_lower)
            if not found_in_this_recipe:
                return False
        return True

    def has_ingredients(self, user_ingredients: List[str]) -> bool:
        # Fuzzy approach
        recipe_ings_lower = [ing.lower() for ing in self.ingredients]
        for ui in user_ingredients:
            # If no fuzzy match found for ui among recipe_ings_lower, fail
            if not any(fuzzy_match_ingredient(ui, ri) for ri in recipe_ings_lower):
                return False
        return True

    def fetch_title_from_pinterest(self) -> None:
            """
            If self.title is empty or whitespace, attempt to fetch the page
            from self.pinterest_url and parse out the real title. If found,
            update self.title. This method can fail if Pinterest requires
            login or if the page is heavily dynamic.

            Usage:
                recipe_obj.fetch_title_from_pinterest()
                # Now recipe_obj.title might be updated with something like "Shrimp Pesto Pasta"
            """
            if self.title and self.title.strip():
                # Already has a non-empty title
                return

            try:
                response = requests.get(self.pinterest_url, timeout=10)
                response.raise_for_status()
            except Exception as e:
                print(f"[ERROR] Could not fetch Pinterest link: {e}")
                return  # Keep self.title as is (probably empty)

            soup = BeautifulSoup(response.text, "html.parser")

            # 1) Try <meta property="og:title" content="...">
            og_title_tag = soup.find("meta", property="og:title")
            if og_title_tag and og_title_tag.get("content"):
                self.title = og_title_tag["content"].strip()
                if self.title:
                    return

            # 2) Fall back to <title>...some text...</title>
            title_tag = soup.find("title")
            if title_tag and title_tag.text.strip():
                self.title = title_tag.text.strip()
                return

            # If we reach here, we found neither
            print("[INFO] No suitable title found on the Pinterest page.")
            # self.title remains empty