import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
from dotenv import load_dotenv

logger = logging.getLogger("TrabajoBot")

ADMIN_USER_ID = int(os.getenv("STEVEID", 0))

def is_owner(ctx):
    """Check if the command user is the bot owner (you)."""
    return ctx.author.id == ADMIN_USER_ID

class AdminCog(commands.Cog):
    """
    Provides admin commands like reloading cogs and server management.
    Fully invisible from the slash command menu.
    """
    cog_name = "Admin"
    cog_description = "Commands for bot maintenance (Owner Only)."
    cog_icon_url = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/72x72/2699.png"  # ⚙️

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ================================================================
    # AUTOCOMPLETE FUNCTIONS FOR SERVER MESSAGING
    # ================================================================
    
    async def guild_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for guild selection"""
        guilds = []
        current_lower = current.lower()
        
        for guild in self.bot.guilds:
            if current_lower in guild.name.lower():
                guilds.append(
                    app_commands.Choice(name=f"{guild.name} ({guild.member_count} members)", value=str(guild.id))
                )
        
        # Return up to 25 suggestions
        return guilds[:25]

    async def channel_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for channel selection based on selected guild"""
        # Get the guild_id from the current command options
        guild_id_str = interaction.namespace.guild
        
        if not guild_id_str:
            return []
        
        try:
            guild_id = int(guild_id_str)
            guild = self.bot.get_guild(guild_id)
            
            if not guild:
                return []
            
            channels = []
            current_lower = current.lower()
            
            # Filter for text channels only
            for channel in guild.text_channels:
                # Check if user has permission to view the channel
                if isinstance(channel, discord.TextChannel):
                    if current_lower in channel.name.lower():
                        channels.append(
                            app_commands.Choice(name=f"#{channel.name}", value=str(channel.id))
                        )
            
            return channels[:25]
        except Exception as e:
            logger.error(f"Error in channel autocomplete: {e}")
            return []

    # ================================================================
    # ADMIN SLASH COMMANDS
    # ================================================================

    @app_commands.command(name="send_message", description="Send a message to a specific channel in any server (Admin only)")
    @app_commands.describe(
        guild="Select a server",
        channel="Select a channel from the server",
        message="The message to send"
    )
    @app_commands.autocomplete(guild=guild_autocomplete)
    @app_commands.autocomplete(channel=channel_autocomplete)
    async def send_message(self, interaction: discord.Interaction, guild: str, channel: str, message: str):
        """Send a message to a specific server and channel"""
        
        # Owner-only check
        if interaction.user.id != ADMIN_USER_ID:
            logger.warning(f"Unauthorized send_message attempt by {interaction.user} (ID: {interaction.user.id})")
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        
        try:
            # Get guild
            guild_id = int(guild)
            target_guild = self.bot.get_guild(guild_id)
            
            if not target_guild:
                logger.error(f"Guild {guild_id} not found")
                return await interaction.followup.send("❌ Guild not found.", ephemeral=True)
            
            # Get channel
            channel_id = int(channel)
            target_channel = target_guild.get_channel(channel_id)
            
            if not target_channel or not isinstance(target_channel, discord.TextChannel):
                logger.error(f"Channel {channel_id} not found in guild {guild_id}")
                return await interaction.followup.send("❌ Channel not found or is not a text channel.", ephemeral=True)
            
            # Send the message
            await target_channel.send(message)
            logger.info(f"Message sent to {target_guild.name}#{target_channel.name} by {interaction.user}")
            
            await interaction.followup.send(
                f"✅ Message sent to **{target_guild.name}** in **#{target_channel.name}**",
                ephemeral=True
            )
            
        except ValueError as e:
            logger.error(f"Invalid ID format: {e}")
            await interaction.followup.send("❌ Invalid server or channel ID.", ephemeral=True)
        except discord.Forbidden:
            logger.error(f"No permission to send message in {channel}")
            await interaction.followup.send("❌ I don't have permission to send messages in that channel.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            await interaction.followup.send(f"❌ Error sending message: {e}", ephemeral=True)

    @commands.command(name="reload")
    async def reload(self, ctx, cog_name: str):
        """Reload a specific cog. Only executable by the bot owner."""
        if not is_owner(ctx):
            return  # Silently fail if not you

        logger.info(f"Reload command invoked by {ctx.author} for {cog_name}")
        await ctx.message.delete()  # Auto-delete command message for stealth

        try:
            await self.bot.reload_extension(f"cogs.{cog_name}")
            logger.info(f"Reloaded cog: {cog_name}")
            await ctx.send(f"✅ Reloaded `{cog_name}` successfully!", delete_after=1)
        except Exception as e:
            logger.error(f"Failed to reload cog {cog_name}: {e}")
            if "has not been loaded" in str(e):
                await self.bot.load_extension(f"cogs.{cog_name}")
                logger.info(f"Loaded cog: {cog_name}")
                await ctx.send(f"✅ Loaded `{cog_name}` successfully!", delete_after=1)
            else:
                logger.error(f"Failed to reload cog {cog_name}: {e}")
                await ctx.send(f"❌ Error reloading `{cog_name}`: {e}", delete_after=5)

    @commands.command(name="reloadall")
    async def reload_all(self, ctx: commands.Context):
        """Reload all cogs in the bot."""
        if not is_owner(ctx):
            return  # Silently fail if not me

        logger.info(f"Reload all command invoked by {ctx.author}")
        await ctx.message.delete()  # Auto-delete command message for stealth
        errors = []
        for cog in list(self.bot.extensions):
            try:
                await self.bot.reload_extension(cog)
                logger.info(f"Reloaded {cog}")
            except Exception as e:
                if "has not been loaded" in str(e):
                    await self.bot.load_extension(cog)
                    logger.info(f"Cog: {cog} not loaded, loading...")
                else:
                    errors.append(f"❌ `{cog}`: {e}")
        if errors:
            await ctx.send("\n".join(errors), delete_after=5)
        else:
            synced = await self.bot.tree.sync()
            logger.info(f"Synced {len(synced)} commands globally.")
            await ctx.send("✅ Reloaded all cogs successfully!", delete_after=1)

    @commands.command(name="shutdown", help="Shuts down the bot (Owner only).")
    async def shutdown_command(self, ctx: commands.Context):
        if not is_owner(ctx):
            logger.warning(f"Unauthorized shutdown attempt by {ctx.author} (ID: {ctx.author.id})")
            return

        logger.warning(f"Shutdown invoked by owner: {ctx.author}")
        await ctx.send("Shutting down... Goodbye!", delete_after=0.5)
        await ctx.message.delete()

        # Close any resources here if needed (db connections, etc.)

        await self.bot.close() # Then close the bot

async def setup(bot: commands.Bot):
    logger.debug("Setting up AdminCog (Owner Only)...")
    await bot.add_cog(AdminCog(bot))
