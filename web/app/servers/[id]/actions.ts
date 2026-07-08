"use server";
import { revalidatePath } from "next/cache";
import { userAccessToken } from "@/auth";
import { fetchUserGuilds, fetchGuildChannels } from "@/lib/discord";
import { query } from "@/lib/db";

const isSnowflake = (v: string) => /^\d{5,25}$/.test(v);
const isCommandName = (v: unknown): v is string =>
  typeof v === "string" && /^[\w-]{1,32}$/.test(v);

async function canManage(guildId: string): Promise<boolean> {
  const token = await userAccessToken();
  if (!token) return false;
  const guilds = await fetchUserGuilds(token);
  return !!guilds?.some((g) => g.id === guildId && g.canManage);
}

/** Enable or disable a set of commands for a guild. Only disabled commands
 *  are stored, so anything unknown (e.g. newly added commands) is enabled. */
export async function setCommands(
  guildId: string,
  commands: string[],
  enabled: boolean
): Promise<{ ok: boolean }> {
  if (
    !isSnowflake(guildId) ||
    !Array.isArray(commands) ||
    commands.length === 0 ||
    commands.length > 100 ||
    !commands.every(isCommandName)
  ) {
    return { ok: false };
  }
  if (!(await canManage(guildId))) return { ok: false };

  if (enabled) {
    await query(
      "DELETE FROM guild_disabled_commands WHERE guild_id = $1 AND command = ANY($2)",
      [guildId, commands]
    );
  } else {
    await query(
      `INSERT INTO guild_disabled_commands (guild_id, command)
       SELECT $1, unnest($2::text[]) ON CONFLICT DO NOTHING`,
      [guildId, commands]
    );
  }
  revalidatePath(`/servers/${guildId}`);
  return { ok: true };
}

/** Set (or clear, with an empty value) the guild's announcement channel. */
export async function setAnnounceChannel(guildId: string, formData: FormData) {
  const channel = formData.get("channel");
  if (!isSnowflake(guildId) || typeof channel !== "string") return;
  if (!(await canManage(guildId))) return;

  if (channel === "") {
    await query("DELETE FROM guild_settings WHERE guild_id = $1", [guildId]);
  } else {
    // The channel must actually belong to this guild.
    const channels = await fetchGuildChannels(guildId);
    if (!channels?.some((c) => c.id === channel)) return;
    await query(
      `INSERT INTO guild_settings (guild_id, announce_channel_id) VALUES ($1, $2)
       ON CONFLICT (guild_id) DO UPDATE SET announce_channel_id = $2`,
      [guildId, channel]
    );
  }
  revalidatePath(`/servers/${guildId}`);
}
