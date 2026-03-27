"""
main.py
=======
 - Loads cogs (music, moderation, fun, etc.)
 - Syncs slash commands
"""

import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Import the logger configuration
from logger import logger

load_dotenv()
intents = discord.Intents.all()


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="?", intents=intents)

    async def setup_hook(self):
        logger.info("Starting bot setup...")

        # ------------------------------------------------------
        # Dynamically load all cogs from the cogs directory
        # ------------------------------------------------------
        cogs_dir = os.path.join(os.path.dirname(__file__), 'cogs')
        for filename in os.listdir(cogs_dir):
            # Check if the file is a Python file and not a special file
            if filename.endswith('.py') and not filename.startswith('_'):
                cog_name = f"cogs.{filename[:-3]}"  # Remove .py and add cogs. prefix
                try:
                    await self.load_extension(cog_name)
                    logger.info(f"Loaded extension: {cog_name}")
                except Exception as e:
                    logger.error(f"Failed to load cog {cog_name}: {e}")

        # Sync commands with Discord
        synced = await self.tree.sync()
        logger.info(f"Synced {len(synced)} commands globally.")

    async def on_ready(self):
        logger.info(f"Bot logged in as {self.user} (ID: {self.user.id})")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="/help"))


if __name__ == "__main__":
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    if not bot_token:
        logger.error("DISCORD_BOT_TOKEN not found in environment. Exiting.")
        exit(1)

    bot = MyBot()
    try:
        logger.info("Attempting to run the bot...")
        bot.run(bot_token)
    except Exception as e:
        logger.error(f"Bot encountered an error: {e}")
