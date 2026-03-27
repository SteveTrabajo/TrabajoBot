# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Bot

```bash
python main.py
```

Requires a `.env` file with: `DISCORD_BOT_TOKEN`, `DB_HOST`, `DB_USER`, `DB_PASS`, `DB_NAME`, `DB_PORT`, `GIPHY_API_KEY`, `STEVEID`, `LIORID`, `SELFID`, `TEST_GUILD_ID`, `LAVALINK_URI`, `LAVALINK_PASSWORD`.

## Architecture

**TrabajoBot** is a Discord bot built with `discord.py` using slash commands (`app_commands`). All features are implemented as **cogs** in `cogs/` and dynamically loaded by `main.py` at startup.

### Core Files

- `main.py` — Bot entry point; defines `MyBot` class, dynamically loads all cogs from `cogs/`, syncs slash commands globally on startup.
- `db.py` — Singleton `Database` class managing a `psycopg2` connection pool (2–10 connections). Used as a context manager: `with self.db.get_connection() as conn`. Supports transactions and auto-creates tables.
- `util/db_utils.py` — `@db_retry()` decorator that retries database calls on transient CockroachDB errors.
- `logger.py` — Timed rotating file handler; writes to `logs/bot_YYYY-MM-DD.log` with 7-day retention. Logger name: `"TrabajoBot"`.

### Cog Pattern

Every cog follows this structure:
```python
class MyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = Database()  # if DB needed

    @app_commands.command(name="...", description="...")
    async def my_command(self, interaction: discord.Interaction, ...):
        await interaction.response.defer()
        # ...
        await interaction.followup.send(...)

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

Cogs with DB access use `@db_retry()` on methods that call the database, and use `with self.db.get_connection() as conn` + `conn.cursor()` for queries.

### Slash Command Conventions

- Commands use `await interaction.response.defer()` before any async work, then `interaction.followup.send()` to respond.
- Owner-only commands check `str(interaction.user.id) == STEVEID` (from env).
- Moderation commands use `@app_commands.default_permissions(kick_members=True)` etc.


### Database Tables

Managed by cogs that create their own tables on first use:
- `birthdays` — managed by `birthdays.py`
- `pickle_sizes`, `pickle_history` — managed by `pickle.py`

### Notable Cogs

- `pickle.py` (largest, ~624 lines) — "Pickle size" game with leaderboard and matplotlib growth graphs. Contains `PickleConfig` and `PickleData` helper classes.
- `admin.py` — Owner-only commands including sending messages as the bot; uses guild/channel autocomplete.
- `music.py` — Music via Wavelink 3.x + Lavalink 4.x. Commands: `/play`, `/skip`, `/pause`, `/stop`, `/queue`, `/nowplaying`, `/volume`, `/loop`, `/shuffle`, `/nightcore`, `/resetfilters`, `/disconnect`. Spotify requires the LavaSrc plugin on the Lavalink server.
