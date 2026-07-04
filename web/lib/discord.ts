// Shared Discord constants and data fetching for the public site.

export const INVITE_URL =
  "https://discord.com/oauth2/authorize?client_id=1000039115183640588";

export interface SlashCommand {
  name: string;
  description: string;
}

export interface CommandCategory {
  name: string;
  emoji: string;
  commands: SlashCommand[];
}

// Maps command names (as registered with Discord) to display categories,
// mirroring the bot's cogs. Unknown commands land in "Other".
const CATEGORY_BY_COMMAND: Record<string, { name: string; emoji: string }> = {
  pickle: { name: "Pickle", emoji: "🍆" },
  pickleboard: { name: "Pickle", emoji: "🍆" },
  picklegraph: { name: "Pickle", emoji: "🍆" },
  setbirthday: { name: "Birthday", emoji: "🎂" },
  mybirthday: { name: "Birthday", emoji: "🎂" },
  birthdaylist: { name: "Birthday", emoji: "🎂" },
  kick: { name: "Moderation", emoji: "🛡️" },
  ban: { name: "Moderation", emoji: "🛡️" },
  unban: { name: "Moderation", emoji: "🛡️" },
  "8ball": { name: "Fun", emoji: "🎉" },
  pew: { name: "Fun", emoji: "🎉" },
  coin: { name: "Fun", emoji: "🎉" },
  userinfo: { name: "Information", emoji: "ℹ️" },
  serverinfo: { name: "Information", emoji: "ℹ️" },
  ping: { name: "Information", emoji: "ℹ️" },
  invite: { name: "Information", emoji: "ℹ️" },
  help: { name: "Help", emoji: "❓" },
  send_message: { name: "Admin", emoji: "⚙️" },
};

const CATEGORY_ORDER = [
  "Pickle",
  "Birthday",
  "Fun",
  "Information",
  "Moderation",
  "Help",
  "Admin",
  "Other",
];

/**
 * Fetches the bot's registered global slash commands from Discord and groups
 * them by category. Returns null when env vars are missing or the API call
 * fails, so the page can render a friendly notice instead of crashing.
 * Revalidated hourly, so newly synced commands show up on their own.
 */
export async function fetchCommandCategories(): Promise<CommandCategory[] | null> {
  const appId = process.env.DISCORD_APP_ID;
  const token = process.env.DISCORD_BOT_TOKEN;
  if (!appId || !token) return null;

  try {
    const res = await fetch(
      `https://discord.com/api/v10/applications/${appId}/commands`,
      {
        headers: { Authorization: `Bot ${token}` },
        next: { revalidate: 3600 },
      }
    );
    if (!res.ok) return null;

    const commands: SlashCommand[] = await res.json();
    const grouped = new Map<string, CommandCategory>();
    for (const cmd of commands) {
      const cat = CATEGORY_BY_COMMAND[cmd.name] ?? { name: "Other", emoji: "✨" };
      if (!grouped.has(cat.name)) {
        grouped.set(cat.name, { name: cat.name, emoji: cat.emoji, commands: [] });
      }
      grouped.get(cat.name)!.commands.push({
        name: cmd.name,
        description: cmd.description,
      });
    }

    for (const category of grouped.values()) {
      category.commands.sort((a, b) => a.name.localeCompare(b.name));
    }
    return [...grouped.values()].sort(
      (a, b) => CATEGORY_ORDER.indexOf(a.name) - CATEGORY_ORDER.indexOf(b.name)
    );
  } catch {
    return null;
  }
}
