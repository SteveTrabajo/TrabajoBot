import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { userAccessToken } from "@/auth";
import { fetchUserGuilds, fetchCommandCategories, fetchGuildChannels } from "@/lib/discord";
import { query } from "@/lib/db";
import ToggleBoard from "./ToggleBoard";
import { setAnnounceChannel } from "./actions";

export const metadata: Metadata = {
  title: "Server settings | TrabajoBot",
};

export default async function ServerSettingsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!/^\d{5,25}$/.test(id)) notFound();

  const token = await userAccessToken();
  const guilds = token ? await fetchUserGuilds(token) : null;
  const guild = guilds?.find((g) => g.id === id && g.canManage);
  // Not logged in, no access, or not their server: pretend it doesn't exist.
  if (!guild) notFound();

  const [categories, disabledRows, channels, settings] = await Promise.all([
    fetchCommandCategories(),
    query<{ command: string }>(
      "SELECT command FROM guild_disabled_commands WHERE guild_id = $1",
      [id]
    ),
    fetchGuildChannels(id),
    query<{ channel: string | null }>(
      "SELECT announce_channel_id::text AS channel FROM guild_settings WHERE guild_id = $1",
      [id]
    ),
  ]);
  const currentChannel = settings[0]?.channel ?? "";

  // The bot owner's admin-only commands don't belong in a guild's toggle list.
  const toggleable = (categories ?? []).filter((c) => c.name !== "Admin");

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <p className="text-sm">
        <Link href="/dashboard" className="text-accent underline">
          ← back to dashboard
        </Link>
      </p>
      <h1 className="mt-2 text-3xl font-bold tracking-tight">{guild.name}</h1>
      <p className="mt-2 text-foreground/60">
        Toggle commands for this server. Changes apply within a minute; new
        commands are enabled automatically.
      </p>

      {channels && (
        <section className="mt-6 rounded-xl border border-white/10 bg-white/[0.03] p-5">
          <h2 className="text-lg font-semibold">📣 Announcement channel</h2>
          <p className="mb-3 mt-1 text-sm text-foreground/50">
            Where monthly pickle resets and birthday wishes are posted. On
            Auto, the first channel named general / bot / announcements is used.
          </p>
          <form
            action={setAnnounceChannel.bind(null, id)}
            className="flex flex-wrap items-center gap-2"
          >
            <select
              name="channel"
              defaultValue={currentChannel}
              className="rounded-md border border-white/15 bg-background px-3 py-1.5 text-sm"
            >
              <option value="">Auto</option>
              {channels.map((c) => (
                <option key={c.id} value={c.id}>
                  #{c.name}
                </option>
              ))}
            </select>
            <button className="rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-white transition hover:opacity-85">
              Save
            </button>
          </form>
        </section>
      )}

      {toggleable.length === 0 ? (
        <div className="mt-10 rounded-xl border border-white/10 bg-white/[0.03] p-8 text-center text-foreground/60">
          Couldn&apos;t load the command list right now. Try again in a bit.
        </div>
      ) : (
        <div className="mt-8">
          <ToggleBoard
            guildId={id}
            categories={toggleable}
            initialDisabled={disabledRows.map((r) => r.command)}
          />
        </div>
      )}
    </div>
  );
}
