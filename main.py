"""
main.py
=======
 - Loads cogs (music, moderation, fun, etc.)
 - Syncs slash commands
"""

import asyncio
import os
import time
import traceback
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
# import wavelink  # disabled — re-enable when Lavalink is back

# Import the logger configuration
from logger import logger
from db import get_database

load_dotenv()
intents = discord.Intents.all()


class GuildFilteredTree(app_commands.CommandTree):
    """Refuses commands disabled per guild via the website's toggle page.

    Only disabled commands are stored (guild_disabled_commands table), so any
    newly added command is enabled everywhere by default.
    """

    _CACHE_TTL = 60.0  # seconds; toggles apply within a minute

    def __init__(self, client):
        super().__init__(client)
        self._disabled_cache = {}

    async def _disabled_for(self, guild_id: int) -> set:
        cached = self._disabled_cache.get(guild_id)
        now = time.monotonic()
        if cached and now - cached[0] < self._CACHE_TTL:
            return cached[1]
        try:
            rows = await asyncio.to_thread(
                get_database().execute,
                "SELECT command FROM guild_disabled_commands WHERE guild_id = %s",
                (guild_id,), fetch='all')
            disabled = {r['command'] for r in rows}
        except Exception as e:
            logger.error(f"Failed to load disabled commands for guild {guild_id}: {e}")
            disabled = cached[1] if cached else set()  # fail open
        self._disabled_cache[guild_id] = (now, disabled)
        return disabled

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id is None or interaction.command is None:
            return True
        if str(interaction.user.id) == os.getenv("STEVEID"):
            return True  # the owner can't lock himself out
        if interaction.command.qualified_name in await self._disabled_for(interaction.guild_id):
            await interaction.response.send_message(
                "This command is disabled in this server.", ephemeral=True)
            return False
        return True

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        # Cooldowns, permission checks and disabled-command refusals are
        # expected; only real failures reach the log and the owner's DMs.
        if isinstance(error, app_commands.CheckFailure):
            return
        command = interaction.command.qualified_name if interaction.command else "?"
        logger.error(f"Unhandled error in /{command}: {error}", exc_info=error)

        owner_id = int(os.getenv("STEVEID", 0))
        if not owner_id:
            return
        try:
            owner = self.client.get_user(owner_id) or await self.client.fetch_user(owner_id)
            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))[-1800:]
            where = interaction.guild.name if interaction.guild else "DM"
            await owner.send(f"⚠️ `/{command}` failed in **{where}**:\n```py\n{tb}\n```")
        except Exception as e:
            logger.error(f"Failed to DM owner about command error: {e}")


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="?", intents=intents, tree_cls=GuildFilteredTree)

    async def setup_hook(self):
        logger.info("Starting bot setup...")

        get_database().ensure_table_exists("guild_disabled_commands", """
            CREATE TABLE IF NOT EXISTS guild_disabled_commands (
                guild_id BIGINT,
                command TEXT,
                PRIMARY KEY (guild_id, command)
            )
        """)
        get_database().ensure_table_exists("guild_settings", """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id BIGINT PRIMARY KEY,
                announce_channel_id BIGINT
            )
        """)

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
