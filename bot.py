import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from clients import GPTClient
from manager import MemoryManager, RecipeManager
from parsers import *
from utils import *

load_dotenv(".env")

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

# Example rules text or welcome message
RULES_TEXT = (
    f"Hello! Thanks for trying the SadMadBot - powered by {OLLAMA_MODEL} .\n\n"
    "Here are a few usage guidelines:\n\n"
    "1) Type `!gpt <question>` to ask.\n"
    "2) I'll remember the last 5 messages.\n"
    "3) Type `!gpt !context` to see recent Q&A.\n"
    "4) Type `!gpt !rules` to see these rules again.\n\n"
    "5) Type `!help_gpt` for more commands.\n\n"
    "6) Type `!recipe <query>` to search @madihowa's food Pinterest board.\n\n"
    "Enjoy!"
)

SYSTEM_PROMPT = """You are a concise, knowledgeable assistant. 
Give brief yet helpful answers, usually 1–5 sentences. 
Include enough detail to address the question thoroughly, 
but do not ramble or include irrelevant commentary or disclaimers. 
If there's prior context in the conversation, use it as needed.
"""

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Create singletons
memory = MemoryManager(max_history=10)
gpt = GPTClient(url=OLLAMA_URL, model=OLLAMA_MODEL)
recipe_manager = RecipeManager()
recipe_manager.load_from_json("data/recipes_all_analyzed.json")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Bot is ready to chat with short-term memory + context commands.")

def chunk_text(text, chunk_size=2000):
    """Split `text` into a list of smaller strings each <= chunk_size."""
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

@bot.command(name="gpt")
async def gpt_command(ctx, *, prompt: str = ""):
    """
    Usage: !gpt <your question here>
    The bot will remember up to 5 total messages in this channel,
    building short conversation context.
    """
    await check_for_new_users(ctx, RULES_TEXT)

    channel_id = str(ctx.channel.id)

    # If the user typed "!gpt !context", we show a summary of Q&A
    if prompt.strip().lower() == "!context":
        summary = memory.summarize_context(channel_id)
        chunks = chunk_text(summary, 2000)
        for chunk in chunks:
            await ctx.send(chunk)
        return

    # If user typed "!gpt !rules"
    if prompt.strip().lower() == "!rules":
        rules_text = (
            "**GPT Bot Rules:**\n"
            "1. Keep questions concise.\n"
            "2. Avoid sending personal info.\n"
            "3. The bot is short-term memory only (5 Q&A long)\n"
        )
        await ctx.send(rules_text)
        return

    # 1) Add user's message
    memory.add_message(channel_id, "User", prompt)

    # 2) Build full prompt
    final_prompt = memory.build_prompt(channel_id)

    # 3) Query GPT
    reply = gpt.query(final_prompt)
    if not reply.strip():
        reply = "*(No response from the model.)*"

    # 4) Add assistant reply to memory
    memory.add_message(channel_id, "Assistant", reply)

    # 5) Send reply (with chunking)
    chunks = chunk_text(reply)
    for chunk in chunks:
        await ctx.send(chunk)

@bot.command(name="help_gpt")
async def help_gpt_command(ctx):
    help_text = (
        "**GPT Bot Help**\n"
        "Usage:\n"
        "`!gpt <your question>` - Ask the GPT.\n"
        "`!gpt !context` - Show recent Q&A summary.\n"
        "`!gpt !rules` - Show usage rules.\n"
    )
    await ctx.send(help_text)

@bot.command(name="recipe")
async def recipe_command(ctx, *, query: str = ""):
    """
    Usage: !recipe <query>
    e.g. "!recipe can i make something with shrimp garlic and onion?"
    We'll parse the query with GPT to extract ingredient words 
    (like ["shrimp","garlic","onion"]) then find matches.
    """
    await check_for_new_users(ctx, RULES_TEXT)

    if not query.strip():
        await ctx.send("Please provide a query about ingredients. e.g. `!recipe shrimp garlic onion`")
        return

    # 1) Extract user ingredients from the query using GPT
    user_ingredients = parse_ingredients_with_llm(query, OLLAMA_URL, OLLAMA_MODEL)
    if not user_ingredients:
        await ctx.send("I couldn't find any ingredients in that query. Please try again.")
        return

    # 2) Find matching recipes
    matched_recipes = recipe_manager.find_recipes_by_ingredients(user_ingredients)
    if not matched_recipes:
        await ctx.send(f"No recipes found matching these ingredients: {user_ingredients}")
        return

    # 3) Show results as multiple embedded messages
    for idx, recipe in enumerate(matched_recipes, start=1):
        # If the JSON has a real title, it’ll show up. Otherwise fallback is domain
        title_to_show = fallback_title_for(recipe)
        domain_part = extract_domain(recipe.source_url)

        embed = discord.Embed(
            title=f"Match #{idx}: {title_to_show}",
            url=recipe.source_url,
            description="Click the title for details."
        )

        # If we want to show the ingredient list
        if recipe.ingredients:
            embed.add_field(
                name="Ingredients",
                value=", ".join(recipe.ingredients),
                inline=False
            )

        # Show the recipe image if present
        if recipe.image_url:
            embed.set_image(url=recipe.image_url)

        # Footer now includes "SadMad Recipe Bot • {domain_part}"
        embed.set_footer(text=f"SadMad Recipe Bot • {domain_part}")

        await ctx.send(embed=embed)

@bot.command(name="food")
async def food_command(ctx, *, query: str = ""):
    """
    Handles queries like:
    - "!food show me N recipes for X type of food"
    - "!food any quick and easy X recipes that I can make?"
    - "!food X recipes that use A,B,C ingredients"
    Uses LLM to parse and RecipeManager to retrieve recipes.
    """
    if not query.strip():
        await ctx.send("Please provide a query. Example: `!food show me 3 recipes for Italian food`.")
        return

    # Parse query using LLM
    parsed_query = parse_query_with_llm(query, OLLAMA_URL, OLLAMA_MODEL)

    if parsed_query["action"] == "error":
        await ctx.send("Sorry, I couldn't understand your query. Please try rephrasing.")
        return

    # Extract parsed details
    action = parsed_query.get("action", "")
    filters = parsed_query.get("filters", {})
    limit = parsed_query.get("limit", 5)

    # Handle actions
    if action in ["show", "find"]:
        food_type = filters.get("type", "").lower()
        ingredients = filters.get("ingredients", [])
        difficulty = filters.get("difficulty", "")

        # Fetch recipes based on filters
        if ingredients:
            recipes = recipe_manager.find_recipes_by_ingredients(ingredients)
        elif difficulty:
            recipes = recipe_manager.get_quick_easy_recipes(food_type)
        else:
            recipes = recipe_manager.get_recipes_by_type(food_type, limit)

        # No recipes found
        if not recipes:
            await ctx.send(f"No recipes found matching your query: {filters}.")
            return

        # Send recipes as embeds
        for recipe in recipes[:limit]:
            embed = discord.Embed(
                title=recipe.title or "Untitled Recipe",
                url=recipe.source_url,
                description=f"Difficulty: {recipe.extra.get('difficulty', 'unknown')} | "
                            f"Time: {recipe.extra.get('time', 'unknown')}",
                color=discord.Color.green()
            )
            embed.add_field(name="Ingredients", value=", ".join(recipe.ingredients) if recipe.ingredients else "N/A", inline=False)
            if recipe.image_url:
                embed.set_image(url=recipe.image_url)
            embed.set_footer(text=f"Source: {recipe.source_url}")

            await ctx.send(embed=embed)

    elif action == "suggest":
        # Suggest general recipes
        recipes = recipe_manager.get_recipes_by_type("", limit)
        if not recipes:
            await ctx.send("Sorry, I couldn't find any recipe suggestions at the moment.")
            return

        for recipe in recipes[:limit]:
            embed = discord.Embed(
                title=recipe.title or "Untitled Recipe",
                url=recipe.source_url,
                description=f"Difficulty: {recipe.extra.get('difficulty', 'unknown')} | "
                            f"Time: {recipe.extra.get('time', 'unknown')}",
                color=discord.Color.blue()
            )
            embed.add_field(name="Ingredients", value=", ".join(recipe.ingredients) if recipe.ingredients else "N/A", inline=False)
            if recipe.image_url:
                embed.set_image(url=recipe.image_url)
            embed.set_footer(text=f"Source: {recipe.source_url}")

            await ctx.send(embed=embed)

    else:
        await ctx.send(
            "I didn't understand that query. Try:\n"
            "- `!food show me 3 recipes for Italian food`\n"
            "- `!food any quick and easy seafood recipes that I can make?`\n"
            "- `!food Italian recipes that use shrimp, garlic, and lemon`"
        )

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)