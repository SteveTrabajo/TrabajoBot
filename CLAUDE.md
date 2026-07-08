# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Two deployables in one repo:

- **TrabajoBot** (repo root, Python): a Discord bot built with `discord.py` slash commands. Runs on **PebbleHost**; auto-restarts roughly every 3 days. Restart it after pushing bot changes, deploys are not automatic.
- **Website** (`web/`, TypeScript): Next.js site with a public landing/commands page, a Discord-login dashboard, per-guild command toggles, and an owner-only admin panel. Deploys automatically on push via **Vercel** (project root directory is `web/`).

Both share one **CockroachDB Cloud** database (cluster `calmer-herring-5909`, aws-eu-central-1). The IP allowlist includes `0.0.0.0/0` (needed for Vercel's rotating IPs). Note: some networks (e.g. campus wifi) block outbound port 26257; if DB connections time out locally, suspect the network first.

## The two Discord applications (important)

| App | ID | Used for |
|---|---|---|
| **TrabajoBot** (production) | `1000039115183640588` | PebbleHost bot, Vercel env vars, invite link in `cogs/info.py` |
| **TestBot** (local dev) | `1157930442188652616` | Local `.env` token, `web/.env.local` |

Any Discord API call must pair a token with **its own** app ID; mixing them returns 403 (code 20012). Local `.env` holds TestBot's token.

## Running

```bash
python main.py            # the bot
cd web && npm run dev     # the site (localhost:3000)
```

Bot `.env` (repo root): `DISCORD_BOT_TOKEN`, `DB_HOST`, `DB_USER`, `DB_PASS`, `DB_NAME`, `DB_PORT`, `GIPHY_API_KEY`, `STEVEID` (owner's Discord ID), `LIORID`, `SELFID`, `TEST_GUILD_ID`.

Website env (`web/.env.local` locally, Vercel settings in production; `web/.env.example` documents them):
`DISCORD_APP_ID`, `DISCORD_BOT_TOKEN`, `AUTH_SECRET` (random, signs session cookies), `AUTH_DISCORD_SECRET` (OAuth client secret; auto-read by Auth.js), `ADMIN_DISCORD_ID` (= STEVEID), `DATABASE_URL` (postgres URL to the same CockroachDB).

## Bot architecture

- `main.py`: entry point. Defines `GuildFilteredTree` (see command toggles below) and `MyBot`; dynamically loads every cog in `cogs/` (except `_DISABLED_COGS = {"music"}`), creates the `guild_disabled_commands` table, syncs slash commands globally.
- `db.py`: `Database` class over a psycopg2 pool (2-10 connections); get the shared instance via `get_database()`. `execute(query, params, commit=, fetch='one'|'all')` returns dict rows; `execute_transaction(queries)` for atomic multi-statement writes.
- `util/db_utils.py`: `@db_retry()` decorator, retries transient CockroachDB errors on async methods.
- `logger.py`: logs to `logs/bot.log`, rotated at UTC midnight to `bot.log.YYYY-MM-DD`, 7-day retention. Logger name `"TrabajoBot"`.

### Conventions

- Cogs follow: `__init__` takes `bot`, gets `self.db = get_database()` if needed, creates its own tables via `ensure_table_exists`. `async def setup(bot)` at file end.
- **psycopg2 is synchronous: every DB call inside async code goes through `await asyncio.to_thread(self.db.execute, ...)`**, otherwise the event loop (heartbeat, all commands) stalls.
- Slash commands: `await interaction.response.defer()` then `interaction.followup.send(...)`, or a single `response.send_message(...)`.
- Owner-only checks compare against `STEVEID` from env.
- matplotlib: use the object-oriented `Figure` API (never pyplot) so graph rendering is thread-safe; backend is forced to Agg.

### CockroachDB gotchas (learned the hard way)

- **Never put `TRUNCATE` in a multi-statement transaction.** In CockroachDB it's a schema change that commits independently, which once caused a double monthly reset. Use `DELETE FROM`.
- CockroachDB `INT` is INT8. The website's `pg` driver returns INT8 as **strings**; cast in SQL (`size::int4`, `user_id::text`) to get usable types.

### Database tables

| Table | Owner | Purpose |
|---|---|---|
| `pickle_sizes` | `pickle.py` | user_id → current month's size |
| `pickle_history` | `pickle.py` | one row per user per month (recorded_at TIMESTAMP; day is irrelevant, month is the unit) |
| `pickle_meta` | `pickle.py` / `birthdays.py` | shared key/value store: `last_rollover` (YYYY-MM), `last_birthday_announce` (YYYY-MM-DD) |
| `birthdays` | `birthdays.py` | user_id → DATE |
| `guild_disabled_commands` | `main.py` | (guild_id, command) rows; a row means that command is disabled there |
| `guild_settings` | `main.py` | guild_id → announce_channel_id; empty/missing row means auto (name-based fallback in `util/announce.py`) |

### The monthly pickle rollover (subtle, don't break it)

`cogs/pickle.py` `_run_rollover()`: daily task at 00:05 UTC plus on startup. It checks `pickle_meta.last_rollover`; if it isn't the current YYYY-MM, it atomically (one transaction) DELETEs `pickle_sizes` and writes the marker, then announces in guilds. Rules:

- History is written by `set_size` at roll time, **never by the rollover**. An old "archive at rollover" step stamped last month's sizes with the new month's date, creating duplicate/ghost history rows; it was removed deliberately.
- Marker commits before the announcement: a missed @everyone beats a double one.
- The announcement crowns each guild's last-month champion (top `pickle_history` size among members) and goes to the guild's announce channel (`util/announce.py`: `guild_settings` row, else name-based fallback).
- The website admin panel can force/suppress a rollover by editing the marker.

### Birthday announcements

`cogs/birthdays.py`: daily task at 06:00 UTC plus startup catch-up, same marker pattern (`last_birthday_announce` in `pickle_meta`). Feb 29 birthdays are announced Feb 28 in non-leap years. Mentions go in message **content** (mentions inside embeds don't ping).

### Per-guild command toggles

`GuildFilteredTree.interaction_check` in `main.py` blocks commands listed in `guild_disabled_commands` (cache TTL 60s, fails open on DB errors, the owner is always allowed). Only **disabled** commands are stored, so new commands are enabled everywhere by default. Toggled from the website (`/servers/[id]`, which also has the announce-channel picker).

### Error reporting

`GuildFilteredTree.on_error` in `main.py` DMs the owner (STEVEID) a truncated traceback for any unhandled command error; `CheckFailure` (cooldowns, permission checks, disabled commands) is filtered out as expected noise.

## Website architecture (`web/`)

Next.js 16 App Router + TypeScript + Tailwind v4. **Read `web/AGENTS.md` and the bundled docs in `web/node_modules/next/dist/docs/` before writing Next.js code; this version differs from training data.** No ORM: raw SQL via `pg` (`web/lib/db.ts`, pooled, max 3). No chart library: pure CSS bars. Dark theme, purple accent `--accent` (the bot's embed color).

| Route | What | Access |
|---|---|---|
| `/` | landing page | public, static |
| `/commands` | slash commands fetched from Discord API, grouped by category, ISR 1h (zero manual upkeep) | public, static |
| `/dashboard` | own pickle size, history chart, birthday view/edit, manageable-servers list | Discord login |
| `/servers` | redirect to `/dashboard` (list moved there) | - |
| `/servers/[id]` | per-command + per-category toggle switches (optimistic UI) + announce-channel picker | Manage Server on that guild, re-checked server-side per action |
| `/admin` | tables editor: current sizes, per-user monthly history, birthdays, rollover marker | `ADMIN_DISCORD_ID` only; everyone else gets 404 |

Key files: `web/auth.ts` (Auth.js v5 beta, Discord provider, scopes `identify guilds`, JWT sessions, helpers `discordUserId()` / `isAdmin()` / `userAccessToken()`), `web/lib/discord.ts` (command + guild fetching; user-guild list cached per token 60s because Discord rate-limits that endpoint hard), `web/app/admin/page.tsx` (all admin server actions).

### Website conventions

- Every server action re-checks authorization first (`isAdmin()` or Manage Server); page-level gating alone is not security.
- Month semantics everywhere: pickle history is monthly; the admin panel edits by YYYY-MM (stored day is a placeholder, the 1st). Current month = `new Date().toISOString().slice(0, 7)` (UTC), matching the bot.
- Any admin edit touching the current month must keep `pickle_sizes` and `pickle_history` in sync (see `syncCurrentSize` in admin actions).
- After mutations: `revalidatePath(...)`. Dynamic pages have `loading.tsx` skeletons.
- Non-admins must never even learn `/admin` exists: `notFound()`, not a 403.

## Writing style for this project

No em dashes in any generated text (chat, docs, commit messages, site copy); use commas, periods, or parentheses. Keep solutions minimal: prefer stdlib/native features, delete over add, smallest working diff.

## Current state / backlog

- Music (`cogs/music.py`, 652 lines) is **disabled** (`_DISABLED_COGS` in main.py, wavelink import commented). A full rework is planned but not designed yet; options were Lavalink-revival vs yt-dlp+FFmpeg.
- `/resetpickles` (TEST_GUILD only) resets the current month only; full data edits belong to the admin panel.
- Watchlist: after each month's 1st, verify the rollover ran exactly once (admin panel shows the marker).
