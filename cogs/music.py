"""
music.py
========
Music commands using Wavelink 3.x + Lavalink 4.x.
Supports YouTube, Spotify (via LavaSrc plugin), SoundCloud, playlists, and free text search.
"""

import asyncio
import logging
import time
from typing import cast
import discord
from discord.ext import commands, tasks
from discord import app_commands, Interaction
import wavelink

logger = logging.getLogger("TrabajoBot")


class MusicCog(commands.Cog):
    cog_name = "Music"
    cog_description = "Play music in voice channels"
    cog_icon = "🎵"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self._audio_watchdog.start()

    async def cog_unload(self):
        self._audio_watchdog.cancel()

    # ---------------------------------------------------------
    # Audio watchdog
    # ---------------------------------------------------------
    @tasks.loop(seconds=10)
    async def _audio_watchdog(self):
        for guild in self.bot.guilds:
            vc = guild.voice_client
            if not isinstance(vc, wavelink.Player):
                continue
            player: wavelink.Player = vc

            # No current track — nothing to monitor.
            if not player.current:
                player._wd_raw = None
                player._wd_pos = None
                continue

            # --- check 1: ask Lavalink's REST API if it's still connected to Discord voice ---
            rest_connected: bool | None = None
            try:
                node = player.node
                if node.session_id:
                    url = f"{node.uri}/v4/sessions/{node.session_id}/players/{guild.id}"
                    headers = {"Authorization": node.password}
                    async with node._session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            rest_connected = data.get("state", {}).get("connected")
                            if not rest_connected:
                                logger.warning(
                                    "Watchdog: Lavalink state.connected=False for guild %s"
                                    " — audio stream dead, reconnecting.",
                                    guild.id,
                                )
                                await self._reconnect_player(player)
                                continue
                        elif resp.status == 404:
                            # Node has no record of this player — it was dropped server-side
                            # without sending a TrackEnd/WebSocketClosed event.
                            logger.warning(
                                "Watchdog: Lavalink returned 404 for guild %s"
                                " — player destroyed server-side, reconnecting.",
                                guild.id,
                            )
                            await self._reconnect_player(player)
                            continue
                        else:
                            logger.warning(
                                "Watchdog: REST returned HTTP %s for guild %s",
                                resp.status, guild.id,
                            )
            except Exception as e:
                logger.warning("Watchdog REST check failed for guild %s: %s", guild.id, e)

            # --- check 2: bot-side voice disconnected but track still set ---
            bot_connected: bool = getattr(player, "_connected", True)
            if not bot_connected:
                logger.warning(
                    "Watchdog: player._connected=False in guild %s but track is set — reconnecting.",
                    guild.id,
                )
                await self._reconnect_player(player)
                continue

            if player.paused:
                continue

            # --- check 3: Lavalink stopped sending playerUpdate events ---
            raw_now: int = getattr(player, "_last_position", 0)
            raw_last: int | None = getattr(player, "_wd_raw", None)
            last_update_ns = getattr(player, "_last_update", None)
            player._wd_raw = raw_now

            elapsed_since_update_ms: int = 0
            if last_update_ns is not None:
                elapsed_since_update_ms = (time.monotonic_ns() - last_update_ns) // 1_000_000

            logger.info(
                "Watchdog guild %s: track=%r rest_connected=%s bot_connected=%s"
                " raw_pos=%sms raw_last=%s elapsed_since_update=%sms",
                guild.id, player.current.title, rest_connected, bot_connected,
                raw_now, raw_last, elapsed_since_update_ms,
            )

            if raw_last is not None and raw_now == raw_last and raw_now > 3000:
                if elapsed_since_update_ms > 15_000:
                    logger.warning(
                        "Watchdog: no Lavalink playerUpdate for %sms in guild %s — reconnecting.",
                        elapsed_since_update_ms, guild.id,
                    )
                    await self._reconnect_player(player)
                    continue

            # --- check 4: ghost track (position capped at track length) ---
            calc_pos: int = player.position
            calc_last: int | None = getattr(player, "_wd_pos", None)
            player._wd_pos = calc_pos
            track_length: int = player.current.length if player.current else 0

            if (
                track_length
                and calc_pos >= track_length
                and calc_last is not None
                and calc_last >= track_length - 1000
            ):
                logger.warning(
                    "Watchdog: ghost track in guild %s (pos=%sms >= length=%sms)"
                    " — Lavalink never fired TrackEnd. Force-skipping.",
                    guild.id, calc_pos, track_length,
                )
                home = getattr(player, "home", None)
                await player.skip(force=True)
                if home:
                    await home.send(
                        "Track got stuck (source timed out) and was skipped automatically.",
                        delete_after=15,
                    )

    @_audio_watchdog.before_loop
    async def _watchdog_before(self):
        await self.bot.wait_until_ready()

    # ---------------------------------------------------------
    # Shared reconnect helper
    # ---------------------------------------------------------
    async def _reconnect_player(self, player: wavelink.Player) -> None:
        """Disconnect and reconnect a player, resuming from the same track and position."""
        channel = player.channel
        current = player.current
        position = player.position
        home = getattr(player, "home", None)

        if not channel:
            return

        try:
            await player.disconnect()
            await asyncio.sleep(1)
            new_player: wavelink.Player = await channel.connect(
                cls=wavelink.Player, timeout=10.0, self_deaf=True
            )
            new_player.home = home
            new_player.autoplay = wavelink.AutoPlayMode.disabled
            if current:
                await new_player.play(current, start=position)
                logger.info("Reconnected and resumed %r at %sms.", current, position)
        except Exception as e:
            logger.error("Reconnect failed: %s", e)
            if home:
                await home.send(
                    "Audio stream died and auto-reconnect failed. Please use `/play` again.",
                    delete_after=20,
                )

    # ---------------------------------------------------------
    # Events
    # ---------------------------------------------------------
    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        logger.info("Wavelink Node connected: %r | Resumed: %s", payload.node, payload.resumed)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload):
        player: wavelink.Player | None = payload.player
        logger.error("Track exception on %r: %s", payload.track, payload.exception)
        home = getattr(player, "home", None)
        if home:
            await home.send(
                f"Failed to play **{payload.track.title}**: `{payload.exception}`",
                delete_after=15,
            )

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player):
        """Fired by Wavelink when the player has been idle for the inactivity timeout."""
        logger.info("Player inactive in guild %s, disconnecting.", player.guild.id)
        home = getattr(player, "home", None)
        await player.disconnect()
        if home:
            await home.send("Left the voice channel due to inactivity.", delete_after=15)

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: wavelink.TrackStuckEventPayload):
        """
        Fired when Lavalink can't buffer audio frames fast enough (common on public nodes).
        Skip the stuck track so playback can continue.
        """
        player: wavelink.Player | None = payload.player
        logger.warning("Track stuck: %r (threshold=%sms) — skipping.", payload.track, payload.threshold)
        home = getattr(player, "home", None)
        if home:
            await home.send(
                f"Track **{payload.track.title}** got stuck, skipping...",
                delete_after=10,
            )
        if player:
            await player.skip(force=True)

    @commands.Cog.listener()
    async def on_wavelink_websocket_closed(self, payload: wavelink.WebsocketClosedEventPayload):
        """
        Fired when Lavalink's UDP/WebSocket connection to Discord voice closes.
        This is the root cause of 'audio stops but track keeps running'.
        We attempt to reconnect the player to restore the audio stream.
        """
        player: wavelink.Player | None = payload.player
        if not player:
            return

        # Code 4014 = bot was forcefully disconnected by a moderator — don't reconnect.
        if payload.code == 4014:
            logger.info("Voice WS closed with 4014 (kicked) in guild %s — not reconnecting.", player.guild.id)
            return

        logger.warning(
            "Voice WebSocket closed in guild %s (code=%s, reason=%r). Reconnecting...",
            player.guild.id, payload.code, payload.reason,
        )

        await self._reconnect_player(player)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player: wavelink.Player | None = payload.player
        if not player:
            return

        track: wavelink.Playable = payload.track
        embed = discord.Embed(title="Now Playing", color=discord.Color.blurple())
        embed.description = f"**{track.title}** by `{track.author}`"

        if track.artwork:
            embed.set_thumbnail(url=track.artwork)

        if track.album.name:
            embed.add_field(name="Album", value=track.album.name)

        if track.length:
            minutes, seconds = divmod(track.length // 1000, 60)
            embed.add_field(name="Duration", value=f"{minutes}:{seconds:02d}")

        home = getattr(player, "home", None)
        if home:
            await home.send(embed=embed)

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    def _get_player(self, interaction: Interaction) -> wavelink.Player | None:
        """Get the existing player for the guild, or None."""
        return cast(wavelink.Player, interaction.guild.voice_client)

    async def _get_or_connect_player(self, interaction: Interaction) -> wavelink.Player | None:
        """
        Connect to the user's voice channel, trying each connected Lavalink node in
        turn until one succeeds. Returns None and sends an error followup on failure.
        Assumes the interaction has already been deferred.
        """
        player = self._get_player(interaction)
        if player:
            if not hasattr(player, "home"):
                player.home = interaction.channel
            return player

        channel = interaction.user.voice.channel

        nodes = list(wavelink.Pool.nodes.values())
        if not nodes:
            await interaction.followup.send("No Lavalink nodes are available right now.", ephemeral=True)
            return None

        for node in nodes:
            # Build a one-off Player subclass that pins itself to this node.
            # This lets us retry each node individually instead of letting
            # Pool.get_node() always hand us the same (possibly broken) one.
            _node = node  # capture for closure

            class _PinnedPlayer(wavelink.Player):
                def __init__(self, client, ch, **kw):
                    super().__init__(client, ch, nodes=[_node], **kw)

            try:
                player = await channel.connect(cls=_PinnedPlayer, timeout=10.0, self_deaf=True)
                player.home = interaction.channel
                player.autoplay = wavelink.AutoPlayMode.disabled
                logger.info("Connected in guild %s via node '%s'.", interaction.guild.id, node.identifier)
                return player
            except wavelink.exceptions.ChannelTimeoutException:
                logger.warning("Node '%s' timed out for guild %s — trying next.", node.identifier, interaction.guild.id)
                # Disconnect any stale voice client and wait until guild.voice_client
                # is actually None before retrying. channel.connect() raises ClientException
                # if a voice client still exists, so we must wait for the Discord round-trip
                # (guild.change_voice_state → VOICE_STATE_UPDATE response) to complete.
                vc = interaction.guild.voice_client
                if vc:
                    try:
                        await vc.disconnect(force=True)
                    except Exception:
                        pass
                for _ in range(10):
                    await asyncio.sleep(0.5)
                    if interaction.guild.voice_client is None:
                        break
            except discord.ClientException as e:
                # Already connected error mid-retry — wait for cleanup and continue.
                if "already connected" in str(e).lower():
                    logger.warning("Voice client still present for guild %s, waiting...", interaction.guild.id)
                    for _ in range(10):
                        await asyncio.sleep(0.5)
                        if interaction.guild.voice_client is None:
                            break
                else:
                    logger.error("Failed to join voice channel: %s", e)
                    await interaction.followup.send("I couldn't join that voice channel.", ephemeral=True)
                    return None
            except AttributeError as e:
                logger.error("Failed to join voice channel: %s", e)
                await interaction.followup.send("I couldn't join that voice channel.", ephemeral=True)
                return None

        await interaction.followup.send(
            f"All {len(nodes)} Lavalink nodes failed to connect. "
            "Public nodes may be down or overloaded — please try again later.",
            ephemeral=True,
        )
        return None

    # ---------------------------------------------------------
    # /play
    # ---------------------------------------------------------
    @app_commands.command(name="play", description="Play a song. Accepts URLs or a search query.")
    @app_commands.describe(
        query="Song name, search query, or URL (Spotify/YouTube/SoundCloud)",
        source="Search source for text queries — ignored if query is a URL (default: SoundCloud)",
    )
    @app_commands.choices(source=[
        app_commands.Choice(name="SoundCloud", value="scsearch"),
        app_commands.Choice(name="YouTube",    value="ytsearch"),
        app_commands.Choice(name="Spotify",    value="spsearch"),
    ])
    async def play(self, interaction: Interaction, query: str, source: str = "scsearch"):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You need to join a voice channel first.", ephemeral=True)
            return

        await interaction.response.defer()

        player = await self._get_or_connect_player(interaction)
        if not player:
            return

        home = getattr(player, "home", None)
        if home and home != interaction.channel:
            await interaction.followup.send(
                f"Music commands must be used in {home.mention}.", ephemeral=True
            )
            return

        # Apply the source prefix for plain-text searches; leave URLs untouched.
        if not query.startswith(("http://", "https://")):
            query = f"{source}:{query}"

        tracks: wavelink.Search = await wavelink.Playable.search(query)
        if not tracks:
            await interaction.followup.send("No tracks found for that query.", ephemeral=True)
            return

        if isinstance(tracks, wavelink.Playlist):
            added: int = await player.queue.put_wait(tracks)
            await interaction.followup.send(
                f"Added playlist **{tracks.name}** — `{added}` tracks to the queue."
            )
        else:
            track: wavelink.Playable = tracks[0]
            await player.queue.put_wait(track)
            await interaction.followup.send(f"Added **{track.title}** to the queue.")

        if not player.playing:
            await player.play(player.queue.get(), volume=80)

    # ---------------------------------------------------------
    # /skip
    # ---------------------------------------------------------
    @app_commands.command(name="skip", description="Skip the current song.")
    async def skip(self, interaction: Interaction):
        player = self._get_player(interaction)
        if not player or not player.playing:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return

        await interaction.response.defer()
        await player.skip(force=True)
        await interaction.followup.send("Skipped.")

    # ---------------------------------------------------------
    # /pause
    # ---------------------------------------------------------
    @app_commands.command(name="pause", description="Pause or resume the player.")
    async def pause(self, interaction: Interaction):
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return

        await interaction.response.defer()
        await player.pause(not player.paused)
        state = "Paused" if player.paused else "Resumed"
        await interaction.followup.send(f"{state}.")

    # ---------------------------------------------------------
    # /stop
    # ---------------------------------------------------------
    @app_commands.command(name="stop", description="Stop playback and clear the queue.")
    async def stop(self, interaction: Interaction):
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return

        await interaction.response.defer()
        player.queue.clear()
        if player.playing:
            await player.skip(force=True)
        await interaction.followup.send("Stopped playback and cleared the queue.")

    # ---------------------------------------------------------
    # /queue
    # ---------------------------------------------------------
    @app_commands.command(name="queue", description="Show the current queue.")
    async def queue(self, interaction: Interaction):
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("No player active.", ephemeral=True)
            return

        await interaction.response.defer()

        queue_list = list(player.queue)
        if not queue_list and not player.current:
            await interaction.followup.send("The queue is empty.")
            return

        embed = discord.Embed(title="Queue", color=discord.Color.blurple())

        if player.current:
            track = player.current
            duration_str = ""
            if track.length:
                minutes, seconds = divmod(track.length // 1000, 60)
                duration_str = f" `{minutes}:{seconds:02d}`"
            embed.add_field(
                name="Now Playing",
                value=f"**{track.title}** by `{track.author}`{duration_str}",
                inline=False
            )

        if queue_list:
            lines = []
            for i, track in enumerate(queue_list[:20], 1):
                duration_str = ""
                if track.length:
                    minutes, seconds = divmod(track.length // 1000, 60)
                    duration_str = f" `{minutes}:{seconds:02d}`"
                lines.append(f"`{i}.` **{track.title}**{duration_str}")

            embed.add_field(name="Up Next", value="\n".join(lines), inline=False)

            if len(queue_list) > 20:
                embed.set_footer(text=f"...and {len(queue_list) - 20} more tracks")

        await interaction.followup.send(embed=embed)

    # ---------------------------------------------------------
    # /nowplaying
    # ---------------------------------------------------------
    @app_commands.command(name="nowplaying", description="Show what's currently playing.")
    async def nowplaying(self, interaction: Interaction):
        player = self._get_player(interaction)
        if not player or not player.current:
            await interaction.response.send_message("Nothing is playing right now.", ephemeral=True)
            return

        await interaction.response.defer()
        track = player.current

        embed = discord.Embed(title="Now Playing", color=discord.Color.blurple())
        embed.description = f"**{track.title}** by `{track.author}`"

        if track.artwork:
            embed.set_thumbnail(url=track.artwork)

        if track.album.name:
            embed.add_field(name="Album", value=track.album.name)

        if track.length:
            minutes, seconds = divmod(track.length // 1000, 60)
            embed.add_field(name="Duration", value=f"{minutes}:{seconds:02d}")

        if player.position and track.length:
            pos_min, pos_sec = divmod(player.position // 1000, 60)
            embed.add_field(name="Position", value=f"{pos_min}:{pos_sec:02d}")

        loop_labels = {
            wavelink.QueueMode.normal: "Off",
            wavelink.QueueMode.loop: "Track",
            wavelink.QueueMode.loop_all: "Queue",
        }
        embed.add_field(name="Loop", value=loop_labels.get(player.queue.mode, "Off"))
        embed.add_field(name="Volume", value=f"{player.volume}%")

        await interaction.followup.send(embed=embed)

    # ---------------------------------------------------------
    # /volume
    # ---------------------------------------------------------
    @app_commands.command(name="volume", description="Set the player volume (0-100).")
    @app_commands.describe(value="Volume level between 0 and 100")
    async def volume(self, interaction: Interaction, value: app_commands.Range[int, 0, 100]):
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("No player active.", ephemeral=True)
            return

        await interaction.response.defer()
        await player.set_volume(value)
        await interaction.followup.send(f"Volume set to `{value}%`.")

    # ---------------------------------------------------------
    # /loop
    # ---------------------------------------------------------
    @app_commands.command(name="loop", description="Set the loop mode.")
    @app_commands.describe(mode="Loop mode: off, track, or queue")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Track", value="track"),
        app_commands.Choice(name="Queue", value="queue"),
    ])
    async def loop(self, interaction: Interaction, mode: str):
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("No player active.", ephemeral=True)
            return

        await interaction.response.defer()
        mode_map = {
            "off": wavelink.QueueMode.normal,
            "track": wavelink.QueueMode.loop,
            "queue": wavelink.QueueMode.loop_all,
        }
        player.queue.mode = mode_map[mode]
        await interaction.followup.send(f"Loop mode set to **{mode}**.")

    # ---------------------------------------------------------
    # /shuffle
    # ---------------------------------------------------------
    @app_commands.command(name="shuffle", description="Shuffle the queue.")
    async def shuffle(self, interaction: Interaction):
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("No player active.", ephemeral=True)
            return

        await interaction.response.defer()
        if player.queue.is_empty:
            await interaction.followup.send("The queue is empty.", ephemeral=True)
            return

        player.queue.shuffle()
        await interaction.followup.send("Queue shuffled.")

    # ---------------------------------------------------------
    # /nightcore
    # ---------------------------------------------------------
    @app_commands.command(name="nightcore", description="Apply a nightcore audio filter (faster + higher pitch).")
    async def nightcore(self, interaction: Interaction):
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("No player active.", ephemeral=True)
            return

        await interaction.response.defer()
        filters: wavelink.Filters = player.filters
        filters.timescale.set(pitch=1.2, speed=1.2, rate=1)
        await player.set_filters(filters)
        await interaction.followup.send("Nightcore filter applied. Use `/resetfilters` to revert.")

    # ---------------------------------------------------------
    # /resetfilters
    # ---------------------------------------------------------
    @app_commands.command(name="resetfilters", description="Reset all audio filters.")
    async def resetfilters(self, interaction: Interaction):
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("No player active.", ephemeral=True)
            return

        await interaction.response.defer()
        filters: wavelink.Filters = player.filters
        filters.reset()
        await player.set_filters(filters)
        await interaction.followup.send("All filters reset.")

    # ---------------------------------------------------------
    # /disconnect
    # ---------------------------------------------------------
    @app_commands.command(name="disconnect", description="Disconnect the bot from the voice channel.")
    async def disconnect(self, interaction: Interaction):
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)
            return

        await interaction.response.defer()
        await player.disconnect()
        await interaction.followup.send("Disconnected.")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
