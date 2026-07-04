"""
pickle.py
========
A Discord bot cog that handles the 'pickle size' game functionality.
Includes commands for checking pickle sizes, leaderboard, and growth tracking graphs.
"""

import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
import matplotlib
matplotlib.use('Agg')  # headless backend; GUI backends crash off the main thread
import matplotlib.style
from matplotlib.figure import Figure
import random
import datetime
import io
import os
from typing import Optional, Tuple, List, Dict
import logging
from db import get_database
from util.db_utils import db_retry

logger = logging.getLogger("TrabajoBot")

matplotlib.style.use('dark_background')

PICKLE_MIN_SIZE = 3
PICKLE_MAX_SIZE = 32
PICKLE_GRAPH_COLOR = 'white'
PICKLE_HIGHLIGHT_COLOR = 'purple'
PICKLE_EMBED_COLOR = discord.Color.purple()
PICKLE_EMOJI = "🍆"
PICKLE_STEVE_ID = int(os.getenv('STEVEID', 0))
PICKLE_LIOR_ID = int(os.getenv('LIORID', 0))
PICKLE_SELF_ID = int(os.getenv('SELFID', 0))

class PickleData:
    """Handles all database operations for the Pickle module.

    psycopg2 is synchronous, so every query goes through asyncio.to_thread
    to keep the event loop (heartbeat, other commands) from stalling on
    CockroachDB round-trips.
    """
    def __init__(self):
        self.db = get_database()
        self._ensure_tables()

    def _ensure_tables(self):
        """Ensures all required tables exist in the database"""
        tables = [
            ("pickle_sizes", """
                CREATE TABLE IF NOT EXISTS pickle_sizes (
                    user_id BIGINT PRIMARY KEY,
                    current_size INTEGER,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """),
            ("pickle_history", """
                CREATE TABLE IF NOT EXISTS pickle_history (
                    user_id BIGINT,
                    size INTEGER,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, recorded_at)
                )
            """),
            ("pickle_meta", """
                CREATE TABLE IF NOT EXISTS pickle_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
        ]
        
        for table_name, creation_query in tables:
            self.db.ensure_table_exists(table_name, creation_query)

    @db_retry()
    async def get_size(self, user_id: int) -> Optional[int]:
        """Get current pickle size for a user"""
        result = await asyncio.to_thread(self.db.execute, "SELECT current_size FROM pickle_sizes WHERE user_id = %s", (user_id,), fetch='one')
        return result['current_size'] if result else None

    @db_retry()
    async def set_size(self, user_id: int, size: int):
        """Set pickle size for a user and record in history"""
        queries = [
            ("""
                INSERT INTO pickle_sizes (user_id, current_size)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET current_size = %s, last_updated = CURRENT_TIMESTAMP
            """, (user_id, size, size)),
            ("""
                INSERT INTO pickle_history (user_id, size)
                VALUES (%s, %s)
            """, (user_id, size))
        ]

        await asyncio.to_thread(self.db.execute_transaction, queries)

    @db_retry()
    async def get_last_rollover(self) -> Optional[str]:
        """Return the YYYY-MM of the last monthly rollover, or None if never run"""
        row = await asyncio.to_thread(self.db.execute, "SELECT value FROM pickle_meta WHERE key = %s", ('last_rollover',), fetch='one')
        return row['value'] if row else None

    @db_retry()
    async def get_leaderboard(self) -> List[Dict]:
        """Get the current pickle size leaderboard"""
        return await asyncio.to_thread(self.db.execute, """
            SELECT user_id, current_size
            FROM pickle_sizes
            ORDER BY current_size DESC
        """, fetch='all')

    @db_retry()
    async def get_history(self, user_id: int, months: int = 12) -> List[Tuple[datetime.date, int]]:
        """Get pickle size history for a user"""
        rows = await asyncio.to_thread(self.db.execute, """
            SELECT recorded_at::date as date, size
            FROM pickle_history
            WHERE user_id = %s
            AND recorded_at > NOW() - (%s * INTERVAL '1 month')
            ORDER BY recorded_at ASC
        """, (user_id, months), fetch='all')
        return [(row['date'], row['size']) for row in rows]


class PickleGraphs:
    """Handles all graph generation for the Pickle module"""
    @staticmethod
    def create_history_graph(history: List[Tuple[datetime.date, int]], user: discord.Member) -> Tuple[io.BytesIO, dict]:
        """Creates a graph of pickle size history.

        Uses the Figure API instead of pyplot: no shared global figure, so
        this is safe to run in a worker thread and can't leak open figures.
        """
        dates = [h[0] for h in history]
        sizes = [h[1] for h in history]
        max_idx = sizes.index(max(sizes))

        fig = Figure(figsize=(10, 6))
        ax = fig.subplots()

        # Create bars, highlighting the best month
        bars = ax.bar([d.strftime('%b') for d in dates], sizes)
        for i, bar in enumerate(bars):
            bar.set_color(PICKLE_HIGHLIGHT_COLOR if i == max_idx else PICKLE_GRAPH_COLOR)

        ax.set_xlabel("Month")
        ax.set_ylabel("Length (cm)")
        ax.set_title(f"{user.display_name}'s Pickle Length - Last 12 Months")

        # Save to BytesIO
        buf = io.BytesIO()
        fig.savefig(buf, format='png')
        buf.seek(0)

        # Calculate stats
        stats = {
            'max_month': dates[max_idx].strftime('%b'),
            'max_size': sizes[max_idx],
            'average': round(sum(sizes) / len(sizes), 2)
        }

        return buf, stats

class PickleBoardView(discord.ui.View):
    """View for the pickle leaderboard with toggle buttons"""
    def __init__(self, cog, guild_id: int, leaderboard_data: List[Dict], guild_members: Dict[int, discord.Member]):
        super().__init__(timeout=180)  # 3 minute timeout
        self.cog = cog
        self.guild_id = guild_id
        self.is_global = False
        self.leaderboard_data = leaderboard_data  # Cache the leaderboard data
        self.guild_members = guild_members  # Cache guild members
        self.global_entries = []  # Cache for global leaderboard entries
        self.server_entries = []  # Cache for server leaderboard entries
        self.message = None
        self.user_cache = {}
        self.page = 0
        self.entries_per_page = 10
        # Hide pagination buttons initially
        self.prev_page.disabled = True
        self.next_page.disabled = True

    async def on_timeout(self):
        """Called when the view times out - removes the buttons"""
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass  # message was deleted or permissions changed
            
    async def prepare_global_leaderboard(self):
        """Pre-fetch global users and prepare global leaderboard entries"""
        try:
            user_ids = [entry['user_id'] for entry in self.leaderboard_data]
            users = await self.bulk_fetch_users(user_ids)
            
            # Build global leaderboard entries
            self.global_entries = []
            for entry in self.leaderboard_data:
                user = users.get(entry['user_id'])
                if user:
                    self.global_entries.append({
                        'name': user.name,
                        'size': entry['current_size']
                    })
            
            # Update pagination buttons
            await self.update_buttons()
            
        except Exception as e:
            logger.error(f"Error preparing global leaderboard: {e}")
            self.global_entries = []

    async def prepare_server_leaderboard(self):
        """Generate server-specific leaderboard entries"""
        self.server_entries = []
        for entry in self.leaderboard_data:
            member = self.guild_members.get(entry['user_id'])
            if member:
                self.server_entries.append({
                    'name': member.name,
                    'size': entry['current_size']
                })
        
        # Update pagination buttons
        await self.update_buttons()

    def get_current_page_content(self) -> str:
        """Get the content for the current page"""
        entries = self.global_entries if self.is_global else self.server_entries
        if not entries:
            return "No pickle sizes recorded yet!"

        start_idx = self.page * self.entries_per_page
        end_idx = start_idx + self.entries_per_page
        current_entries = entries[start_idx:end_idx]
        
        if not current_entries:
            return "No entries on this page."
        
        lb_text = []
        for i, entry in enumerate(current_entries, start=start_idx + 1):
            lb_text.append(f"**{i}.** {entry['name']} - **{entry['size']}** cm")
        
        total_pages = (len(entries) + self.entries_per_page - 1) // self.entries_per_page
        page_info = f"\n\nPage {self.page + 1}/{total_pages}" if total_pages > 1 else ""
        return "\n".join(lb_text) + page_info

    async def update_buttons(self):
        """Update the state of pagination buttons"""
        entries = self.global_entries if self.is_global else self.server_entries
        total_pages = (len(entries) + self.entries_per_page - 1) // self.entries_per_page
        
        self.prev_page.disabled = self.page <= 0
        self.next_page.disabled = self.page >= total_pages - 1
        
        # Only show pagination buttons if there's more than one page
        self.prev_page.style = discord.ButtonStyle.secondary
        self.next_page.style = discord.ButtonStyle.secondary

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page"""
        self.page = max(0, self.page - 1)
        await self.update_leaderboard(interaction)

    @discord.ui.button(label="Show Global", style=discord.ButtonStyle.primary, row=1)
    async def toggle_global(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle between global and server leaderboard"""
        await interaction.response.defer()
        self.page = 0  # Reset to first page when switching views
        
        if self.is_global:
            # Switch to server view
            button.label = "Show Global"
            self.is_global = False
            button.disabled = False  # Enable button for server view
            await self.update_leaderboard(interaction)
        else:
            # Switch to global view and disable button while loading
            button.label = "Loading..."
            button.disabled = True
            self.is_global = True
            
            # Update message to show loading state
            embed = discord.Embed(
                title=f"{PICKLE_EMOJI} Global Pickle Leaderboard {PICKLE_EMOJI}",
                description="Loading global leaderboard...",
                color=PICKLE_EMBED_COLOR
            )
            await interaction.edit_original_response(embed=embed, view=self)
            
            # Load global data if needed
            if not self.global_entries:
                await self.prepare_global_leaderboard()
            
            # Re-enable button and update label
            button.label = "Show Server"
            button.disabled = False
            await self.update_leaderboard(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page"""
        entries = self.global_entries if self.is_global else self.server_entries
        total_pages = (len(entries) + self.entries_per_page - 1) // self.entries_per_page
        self.page = min(self.page + 1, total_pages - 1)
        await self.update_leaderboard(interaction)

    async def bulk_fetch_users(self, user_ids: List[int]) -> Dict[int, discord.User]:
        """Resolve users, preferring discord.py's local cache over API fetches"""
        for uid in user_ids:
            if uid not in self.user_cache:
                user = self.cog.bot.get_user(uid)
                if user is None:
                    try:
                        user = await self.cog.bot.fetch_user(uid)
                    except Exception:
                        continue
                self.user_cache[uid] = user
        return {uid: self.user_cache[uid] for uid in user_ids if uid in self.user_cache}

    async def update_leaderboard(self, interaction: discord.Interaction):
        """Update the leaderboard message"""
        try:
            if not self.leaderboard_data:
                await interaction.response.edit_message(content="No pickle sizes recorded yet!", view=self)
                return

            # Get content for current page
            description = self.get_current_page_content()
            
            # If global view isn't ready yet, show loading message
            if self.is_global and not self.global_entries:
                description = "Loading global leaderboard..."

            embed = discord.Embed(
                title=f"{PICKLE_EMOJI} {'Global' if self.is_global else 'Server'} Pickle Leaderboard {PICKLE_EMOJI}",
                description=description,
                color=PICKLE_EMBED_COLOR
            )
            
            # Update button states
            await self.update_buttons()
            
            # If interaction isn't responded to yet (like in deferred responses)
            try:
                await interaction.response.edit_message(embed=embed, view=self)
            except Exception:
                if self.message:
                    await self.message.edit(embed=embed, view=self)
            
        except Exception as e:
            logger.error(f"Error updating leaderboard: {e}")
            await interaction.response.edit_message(
                content="Sorry, something went wrong updating the leaderboard!", 
                view=self
            )


class Pickle(commands.Cog):
    """A cog that handles the pickle size game functionality"""
    cog_name = "Pickle"
    cog_description = "Pickle commands"
    cog_icon_url = "https://cdn3.emoji.gg/emojis/1774-hd-eggplant.png"
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = PickleData()
        self.monthly_reset.start()

    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.monthly_reset.cancel()

    # Fires daily at 00:05 UTC and on startup; the pickle_meta marker makes it
    # run at most once per month, so a missed month is caught up on the next run.
    @tasks.loop(time=datetime.time(hour=0, minute=5, tzinfo=datetime.timezone.utc))
    async def monthly_reset(self):
        await self._run_rollover()

    @monthly_reset.before_loop
    async def before_monthly_reset(self):
        await self.bot.wait_until_ready()
        await self._run_rollover()

    async def _run_rollover(self):
        """Reset sizes and nudge chat, at most once per calendar month."""
        month_key = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
        try:
            if await self.data.get_last_rollover() == month_key:
                return
        except Exception as e:
            logger.error(f"Failed to read rollover marker: {e}")
            return

        logger.info(f"Running monthly pickle rollover for {month_key}...")
        try:
            # Archive current sizes, wipe them, and record the rollover atomically.
            queries = [
                ("""
                    INSERT INTO pickle_history (user_id, size)
                    SELECT user_id, current_size
                    FROM pickle_sizes
                    WHERE NOT EXISTS (
                        SELECT 1 FROM pickle_history
                        WHERE pickle_history.user_id = pickle_sizes.user_id
                        AND DATE_TRUNC('month', recorded_at) = DATE_TRUNC('month', CURRENT_TIMESTAMP)
                    )
                """, ()),
                # DELETE, not TRUNCATE: in CockroachDB TRUNCATE is a schema change
                # that commits independently of this transaction, so the wipe could
                # succeed while the marker below failed -> double reset on restart.
                ("DELETE FROM pickle_sizes", ()),
                ("""
                    INSERT INTO pickle_meta (key, value) VALUES ('last_rollover', %s)
                    ON CONFLICT (key) DO UPDATE SET value = %s
                """, (month_key, month_key)),
            ]
            await asyncio.to_thread(self.data.db.execute_transaction, queries)
            logger.info("Monthly pickle rollover completed successfully")
        except Exception as e:
            logger.error(f"Failed to perform monthly pickle rollover: {e}")
            return

        # Best-effort nudge. The marker is already committed, so a failed send
        # is not retried; a missed nudge beats a double @everyone.
        await self._notify_new_month()

    async def _notify_new_month(self):
        for guild in self.bot.guilds:
            try:
                channel = next((ch for ch in guild.text_channels if ch.name in ['general', '🍁general', 'bot', 'bot-commands', 'announcements', 'special-operations']), None)
                if channel:
                    await channel.send(
                        content="@everyone",
                        allowed_mentions=discord.AllowedMentions(everyone=True),
                        embed=discord.Embed(
                            title=f"{PICKLE_EMOJI} Monthly Pickle Reset {PICKLE_EMOJI}",
                            description="All pickle sizes have been reset for the new month! Use `/pickle` to get your new size!",
                            color=PICKLE_EMBED_COLOR
                        )
                    )
            except Exception as e:
                logger.error(f"Failed to send reset notification in guild {guild.name}: {e}")

    def _get_size_message(self, user: discord.Member, size: int, is_new: bool, mentioned_by: Optional[discord.Member] = None) -> str:
        """Generate appropriate message based on user and size"""
        # If the bot itself is mentioned
        if user.id == PICKLE_SELF_ID:
            if mentioned_by and mentioned_by.id == PICKLE_STEVE_ID:
                return f"**Oh master, my pickle size could never be as big as yours.**\n\nIt is a mere **{size} cm**."
            else:
                return f"I dunno, maybe ask your mom?\n\nJK, it's **{size}** cm."
        
        # If Steve is mentioned or uses the command
        elif user.id == PICKLE_STEVE_ID:
            if is_new:
                if size > 25:
                    return f"**Master! You did well this month.**\nYour pickle size is **{size} cm**! {PICKLE_EMOJI}"
                else:
                    return f"**I am so sorry master, I have failed you.**\nYour peepee is **{size} cm** this month {PICKLE_EMOJI}"
            else:
                return f"Master, your pickle size is **{size} cm**! {PICKLE_EMOJI}"
        
        # If Lior is mentioned or uses the command
        elif user.id == PICKLE_LIOR_ID:
            if mentioned_by:  # Someone mentioned Lior
                if size < 10:
                    return f"Pfft, pathetic. **Lior**'s size this month is just **{size} cm**.\nShameful {PICKLE_EMOJI}"
                else:
                    return f"Looks like **Lior** got lucky this month.\nHe got a whopping **{size} cm**. {PICKLE_EMOJI}"
            else:  # Lior used the command
                if size > 10:
                    return f"**DAMN Lior! You got lucky this month.**\nYour pickle size is **{size} cm**! {PICKLE_EMOJI}"
                else:
                    return f"**HAH! Smol PP as always.**\nThose **{size} cm** couldn't even satisfy a fleshlight! {PICKLE_EMOJI}"
        
        # For everyone else
        else:
            return f"**{user.display_name}**'s pickle size is **{size} cm**! {PICKLE_EMOJI}"

    @app_commands.command(name="pickle", description="Shows the size of your pickle")
    async def pickle(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Check pickle size for yourself or another member"""
        target = member or interaction.user
        mentioned_by = interaction.user if member else None
        
        try:
            size = await self.data.get_size(target.id)
            is_new = size is None
            
            if is_new:
                size = random.randint(PICKLE_MIN_SIZE, PICKLE_MAX_SIZE)
                await self.data.set_size(target.id, size)
                
            message = self._get_size_message(target, size, is_new, mentioned_by)
            embed = discord.Embed(description=message, color=PICKLE_EMBED_COLOR)
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in pickle command: {e}")
            await interaction.response.send_message(
                "Sorry, something went wrong checking that pickle size!", 
                ephemeral=True
            )

    @app_commands.command(name="pickleboard", description="Shows the pickle size leaderboard")
    async def pickleboard(self, interaction: discord.Interaction):
        """Display the pickle size leaderboard"""
        try:
            # Defer the response since we'll need a moment to prepare the data
            await interaction.response.defer()
            
            leaderboard = await self.data.get_leaderboard()
            
            if not leaderboard:
                await interaction.followup.send("No pickle sizes recorded yet!")
                return

            # Get all guild members once
            guild_members = {m.id: m for m in interaction.guild.members}
            
            # Create view with buttons and pass all necessary data
            view = PickleBoardView(self, interaction.guild_id, leaderboard, guild_members)
            
            # Prepare the server leaderboard data first
            await view.prepare_server_leaderboard()
            
            # Create initial embed with the server leaderboard
            embed = discord.Embed(
                title=f"{PICKLE_EMOJI} Server Pickle Leaderboard {PICKLE_EMOJI}",
                description=view.get_current_page_content(),
                color=PICKLE_EMBED_COLOR
            )
            
            # Send the message with the prepared data
            message = await interaction.followup.send(embed=embed, view=view)
            view.message = message
            
            # Start background task for global data
            asyncio.create_task(view.prepare_global_leaderboard())
            
        except Exception as e:
            logger.error(f"Error in pickleboard command: {e}")
            await interaction.followup.send(
                "Sorry, something went wrong fetching the leaderboard!",
                ephemeral=True
            )

    @app_commands.command(name="picklegraph", description="Shows your pickle size history graph")
    async def picklegraph(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Display a graph of pickle size history"""
        target = member or interaction.user
        
        try:
            history = await self.data.get_history(target.id)
            
            if not history:
                embed = discord.Embed(
                    description=f"No pickle history found for **{target.display_name}**.\n"
                              f"Use `/pickle` first!",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed)
                return

            # Generate graph in a thread to avoid blocking the event loop
            graph_buf, stats = await asyncio.to_thread(PickleGraphs.create_history_graph, history, target)
            
            # Create embed
            embed = discord.Embed(
                title="Yearly Pickle Length History",
                color=PICKLE_EMBED_COLOR,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            
            # Add stats
            embed.add_field(
                name="Best Month", 
                value=f"**{stats['max_month']}** - {stats['max_size']} cm", 
                inline=True
            )
            embed.add_field(
                name="Average", 
                value=f"{stats['average']} cm", 
                inline=True
            )
            
            # Set author and images
            embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
            embed.set_thumbnail(url='https://cdn3.emoji.gg/emojis/1774-hd-eggplant.png')
            
            # Send response
            file = discord.File(graph_buf, filename='pickle_history.png')
            embed.set_image(url='attachment://pickle_history.png')
            
            await interaction.response.send_message(
                content=f"||{target.mention}||",
                file=file,
                embed=embed
            )
            
        except Exception as e:
            logger.error(f"Error in picklegraph command: {e}")
            await interaction.response.send_message(
                "Sorry, something went wrong generating the graph!", 
                ephemeral=True
            )

    @app_commands.command(name="resetpickles", description="Reset all pickle sizes (Admin only)")
    @app_commands.guilds(discord.Object(id=int(os.getenv("TEST_GUILD_ID", 0))))
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_pickles(self, interaction: discord.Interaction):
        """Reset all pickle sizes (Admin only)"""
        try:
            await asyncio.to_thread(self.data.db.execute, "TRUNCATE TABLE pickle_sizes, pickle_history", commit=True)
            await interaction.response.send_message(
                "All pickle sizes have been reset!", 
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in reset_pickles command: {e}")
            await interaction.response.send_message(
                "Sorry, something went wrong resetting the pickle sizes!", 
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Pickle(bot))