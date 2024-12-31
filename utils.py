import json

import discord
import tldextract


def fallback_title_for(recipe) -> str:
    """
    If recipe.title is empty, fallback to domain name of recipe.source_url.
    Otherwise, use the stored title.
    """
    if recipe.title and recipe.title.strip():
        return recipe.title
    return extract_domain(recipe.source_url)

def save_seen_users(seen_users):
    with open("seen_users.json", "w") as f:
        json.dump(list(seen_users), f)

def load_seen_users():
    try:
        with open("seen_users.json", "r") as f:
            data = json.load(f)
            seen_users = set(data)
    except FileNotFoundError:
        seen_users = set()

    return seen_users

def extract_domain(url: str) -> str:
    """
    Returns something like "pinterest.com" 
    given a full URL. 
    If the domain is not found, returns "untitled".
    """
    parsed = tldextract.extract(url)
    domain_part = f"{parsed.domain}.{parsed.suffix}" if parsed.suffix else parsed.domain
    return domain_part if domain_part else "untitled"

async def check_for_new_users(ctx, rules: str):
    """
    Checks if the user has already received the DM with the rules.
    If not, sends the DM and marks the user as seen.
    """
    seen_users = load_seen_users()
    if ctx.author.id not in seen_users:
        try:
            await ctx.author.send(rules)
        except discord.Forbidden:
            # If the user has DMs disabled, skip
            pass
        except Exception as e:
            print(f"Error sending DM to user {ctx.author.id}: {e}")

        # Mark the user as seen
        seen_users.add(ctx.author.id)
        save_seen_users(seen_users)