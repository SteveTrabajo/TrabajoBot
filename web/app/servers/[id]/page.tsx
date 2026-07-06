import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { userAccessToken } from "@/auth";
import { fetchUserGuilds, fetchCommandCategories } from "@/lib/discord";
import { query } from "@/lib/db";
import ToggleBoard from "./ToggleBoard";

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

  const [categories, disabledRows] = await Promise.all([
    fetchCommandCategories(),
    query<{ command: string }>(
      "SELECT command FROM guild_disabled_commands WHERE guild_id = $1",
      [id]
    ),
  ]);

  // The bot owner's admin-only commands don't belong in a guild's toggle list.
  const toggleable = (categories ?? []).filter((c) => c.name !== "Admin");

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <p className="text-sm">
        <Link href="/servers" className="text-accent underline">
          ← all servers
        </Link>
      </p>
      <h1 className="mt-2 text-3xl font-bold tracking-tight">{guild.name}</h1>
      <p className="mt-2 text-foreground/60">
        Toggle commands for this server. Changes apply within a minute; new
        commands are enabled automatically.
      </p>

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
