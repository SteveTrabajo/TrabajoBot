"""
announce.py
===========
Resolves which channel a guild wants bot announcements in (pickle resets,
birthdays). A guild can set one on the website (guild_settings table);
otherwise the first channel matching the classic name list is used.
"""

import asyncio
import logging

logger = logging.getLogger("TrabajoBot")

FALLBACK_CHANNEL_NAMES = ['general', '🍁general', 'bot', 'bot-commands', 'announcements', 'special-operations']


async def get_announce_channel(guild):
    """The guild's configured announcement channel, or a name-based fallback, or None."""
    from db import get_database
    try:
        row = await asyncio.to_thread(
            get_database().execute,
            "SELECT announce_channel_id FROM guild_settings WHERE guild_id = %s",
            (guild.id,), fetch='one')
        if row and row['announce_channel_id']:
            channel = guild.get_channel(int(row['announce_channel_id']))
            if channel:
                return channel
            logger.warning(f"Configured announce channel {row['announce_channel_id']} not found in {guild.name}, falling back")
    except Exception as e:
        logger.error(f"Failed to read announce channel for guild {guild.id}: {e}")
    return next((ch for ch in guild.text_channels if ch.name in FALLBACK_CHANNEL_NAMES), None)
