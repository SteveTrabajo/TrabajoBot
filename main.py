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
# import wavelink  # disabled — re-enable when Lavalink is back

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
        _DISABLED_COGS = {"music"}  # re-enable when wavelink is back
        for filename in os.listdir(cogs_dir):
            # Check if the file is a Python file and not a special file
            if filename.endswith('.py') and not filename.startswith('_') and filename[:-3] not in _DISABLED_COGS:
                cog_name = f"cogs.{filename[:-3]}"  # Remove .py and add cogs. prefix
                try:
                    await self.load_extension(cog_name)
                    logger.info(f"Loaded extension: {cog_name}")
                except Exception as e:
                    logger.error(f"Failed to load cog {cog_name}: {e}")

        # Wavelink/Lavalink disabled — re-enable by restoring the import and this block
        # _PUBLIC_NODES = [
        #     wavelink.Node(identifier="serenetia", uri="http://lavalinkv4.serenetia.com:80",   password="https://seretia.link/discord"),
        #     wavelink.Node(identifier="nyxbot-sg1", uri="http://sg1-nodelink.nyxbot.app:3000", password="nyxbot.app/support"),
        #     wavelink.Node(identifier="nyxbot-sg2", uri="http://sg2-nodelink.nyxbot.app:3000", password="nyxbot.app/support"),
        #     wavelink.Node(identifier="g3v",        uri="http://lava.g3v.co.uk:9008",          password="lavalinklol"),
        #     wavelink.Node(identifier="jirayu",     uri="http://lavalink.jirayu.net:13592",    password="youshallnotpass"),
        #     wavelink.Node(identifier="nexcloud",   uri="http://n3.nexcloud.in:2026",           password="nexcloud"),
        # ]
        # _custom_uri = os.getenv("LAVALINK_URI")
        # _custom_pass = os.getenv("LAVALINK_PASSWORD")
        # if _custom_uri and _custom_pass:
        #     if not _custom_uri.startswith(("http://", "https://")):
        #         _custom_uri = f"http://{_custom_uri}"
        #     _PUBLIC_NODES.insert(0, wavelink.Node(identifier="custom", uri=_custom_uri, password=_custom_pass))
        # try:
        #     await wavelink.Pool.connect(nodes=_PUBLIC_NODES, client=self, cache_capacity=100)
        #     logger.info("Connected to %d Lavalink node(s).", len(_PUBLIC_NODES))
        # except Exception as e:
        #     logger.error("Failed to connect to any Lavalink node: %s", e)

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
