"""
birthdays.py
============
A Cog for storing and retrieving user birthdays in CockroachDB using the connection pool.
"""

import asyncio
import calendar
import logging
import datetime
import discord
from discord.ext import commands, tasks
from discord import app_commands, Interaction
from db import get_database
from util.announce import get_announce_channel

logger = logging.getLogger("TrabajoBot")

class BirthdaysCog(commands.Cog):
    """
    Provides slash commands to set a birthday, view your birthday, and list all
    birthdays in the server. Announces birthdays once a day.
    """
    cog_name = "Birthday"
    cog_description = "Birthday tracking commands."
    cog_icon_url = "https://cdn-icons-png.flaticon.com/512/2004/2004422.png"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = get_database()

        # Ensure the table exists
        creation_query = """
        CREATE TABLE IF NOT EXISTS birthdays (
            user_id BIGINT PRIMARY KEY,
            birthday_date DATE NOT NULL
        )
        """
        self.db.ensure_table_exists("birthdays", creation_query)
        # Shared key/value table (created by pickle.py too); holds the
        # announcement marker so restarts can't double-post.
        self.db.ensure_table_exists("pickle_meta", """
            CREATE TABLE IF NOT EXISTS pickle_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        self.birthday_announcer.start()
        logger.debug("BirthdaysCog initialized with database table check.")

    async def cog_unload(self):
        self.birthday_announcer.cancel()

    # Fires daily at 06:00 UTC and on startup; the marker makes it run at
    # most once per day, so a missed morning is caught up on the next start.
    @tasks.loop(time=datetime.time(hour=6, tzinfo=datetime.timezone.utc))
    async def birthday_announcer(self):
        await self._announce_birthdays()

    @birthday_announcer.before_loop
    async def before_birthday_announcer(self):
        await self.bot.wait_until_ready()
        await self._announce_birthdays()

    @staticmethod
    def _birthday_keys(today: datetime.date) -> list:
        """MM-DD keys to match today; Feb 29 folks celebrate on Feb 28 off-leap-years."""
        keys = [today.strftime("%m-%d")]
        if today.month == 2 and today.day == 28 and not calendar.isleap(today.year):
            keys.append("02-29")
        return keys

    async def _announce_birthdays(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        try:
            row = await asyncio.to_thread(
                self.db.execute,
                "SELECT value FROM pickle_meta WHERE key = %s", ('last_birthday_announce',), fetch='one')
            if row and row['value'] == today.isoformat():
                return
            rows = await asyncio.to_thread(
                self.db.execute,
                "SELECT user_id FROM birthdays WHERE to_char(birthday_date, 'MM-DD') = ANY(%s)",
                (self._birthday_keys(today),), fetch='all')
            # Marker before sending: a missed greeting beats a double ping
            # if the bot crashes mid-send (same policy as the pickle rollover).
            await asyncio.to_thread(
                self.db.execute,
                """INSERT INTO pickle_meta (key, value) VALUES ('last_birthday_announce', %s)
                   ON CONFLICT (key) DO UPDATE SET value = %s""",
                (today.isoformat(), today.isoformat()), commit=True)
        except Exception as e:
            logger.error(f"Birthday announcement DB step failed: {e}")
            return

        if not rows:
            return
        user_ids = [int(r['user_id']) for r in rows]
        for guild in self.bot.guilds:
            members = [m for uid in user_ids if (m := guild.get_member(uid))]
            if not members:
                continue
            channel = await get_announce_channel(guild)
            if not channel:
                continue
            mentions = " ".join(m.mention for m in members)
            try:
                await channel.send(
                    content=f"🎂 Happy birthday {mentions}! 🎉",
                    allowed_mentions=discord.AllowedMentions(users=True),
                )
            except Exception as e:
                logger.error(f"Failed to send birthday message in {guild.name}: {e}")

    @app_commands.command(name="setbirthday", description="Set your birthday (YYYY-MM-DD).")
    @app_commands.describe(date="The date of your birthday (YYYY-MM-DD)")
    async def set_birthday(self, interaction: Interaction, date: str):
        logger.info(f"/setbirthday invoked by {interaction.user} with date {date}")
        
        # Defer the interaction immediately to prevent timeout
        await interaction.response.defer(thinking=True, ephemeral=False)
    
        try:
            # Parse the date string
            bday = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            logger.warning("Invalid date format provided.")
            # Send follow-up if the date is invalid
            return await interaction.followup.send("Invalid date format. Please use YYYY-MM-DD.")
    
        # Execute the database query
        query = """
            INSERT INTO birthdays (user_id, birthday_date)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE
              SET birthday_date = EXCLUDED.birthday_date
        """
        try:
            self.db.execute(query, (interaction.user.id, bday), commit=True)
            logger.debug(f"Birthday set for user {interaction.user.id} to {bday}")
            await interaction.followup.send(f"Birthday set to {bday} for {interaction.user.mention}")
        except Exception as e:
            logger.error(f"Database error when setting birthday: {e}")
            await interaction.followup.send("An error occurred while setting your birthday. Please try again later.")

    @app_commands.command(name="mybirthday", description="Check your stored birthday.")
    async def my_birthday(self, interaction: Interaction):
        logger.info(f"/mybirthday invoked by {interaction.user}")
        await interaction.response.defer(thinking=True, ephemeral=False)
        query = """
            SELECT birthday_date
            FROM birthdays
            WHERE user_id = %s
        """
        try:
            row = self.db.execute(query, (interaction.user.id,), fetch='one')
            if row:
                logger.debug(f"User {interaction.user.id} birthday: {row['birthday_date']}")
                await interaction.followup.send(f"Your birthday is set to **{row['birthday_date']}**.")
            else:
                logger.debug(f"No birthday found for user {interaction.user.id}")
                await interaction.followup.send("No birthday set. Use /setbirthday to set it.")
        except Exception as e:
            logger.error(f"Database error when fetching birthday: {e}")
            await interaction.followup.send("An error occurred while fetching your birthday. Please try again later.")

    @app_commands.command(name="birthdaylist", description="List all birthdays in this server.")
    async def birthday_list(self, interaction: Interaction):
        logger.info(f"/birthdaylist invoked by {interaction.user}")
        await interaction.response.defer(thinking=True, ephemeral=False)
        query = """
            SELECT user_id, birthday_date
            FROM birthdays
            ORDER BY birthday_date
        """
        try:
            rows = self.db.execute(query, (), fetch='all')
            if not rows:
                logger.debug("No birthdays found.")
                return await interaction.followup.send("No birthdays found.")

            lines = []
            for row in rows:
                user_id = row["user_id"]
                birthday = row["birthday_date"]
                # Check if the user is in the current server
                member = interaction.guild.get_member(user_id)
                if member is not None:
                    lines.append(f"{member.mention} - {birthday}")

            if not lines:
                return await interaction.followup.send("No birthdays found for members in this server.")

            # Chunk output to stay within Discord's 2000-character message limit
            chunk, chunks = [], []
            for line in lines:
                if sum(len(l) + 1 for l in chunk) + len(line) > 1900:
                    chunks.append("\n".join(chunk))
                    chunk = []
                chunk.append(line)
            if chunk:
                chunks.append("\n".join(chunk))

            for piece in chunks:
                await interaction.followup.send(piece)
        except Exception as e:
            logger.error(f"Database error when fetching birthday list: {e}")
            await interaction.followup.send("An error occurred while fetching the birthday list. Please try again later.")

async def setup(bot: commands.Bot):
    logger.debug("Setting up BirthdaysCog...")
    await bot.add_cog(BirthdaysCog(bot))
