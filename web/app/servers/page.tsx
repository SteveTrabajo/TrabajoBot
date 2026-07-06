import type { Metadata } from "next";
import Link from "next/link";
import { auth, signIn, signOut, userAccessToken } from "@/auth";
import { fetchUserGuilds, fetchBotGuildIds } from "@/lib/discord";

export const metadata: Metadata = {
  title: "Servers | TrabajoBot",
};

export default async function ServersPage() {
  const session = await auth();

  if (!session?.user) {
    return (
      <div className="mx-auto max-w-md px-4 py-20">
        <div className="flex flex-col items-center gap-4 rounded-xl border border-white/10 bg-white/[0.03] p-10 text-center">
          <h1 className="text-2xl font-bold">Your servers</h1>
          <p className="text-sm text-foreground/60">
            Sign in with Discord to manage TrabajoBot in your servers.
          </p>
          <form
            action={async () => {
              "use server";
              await signIn("discord", { redirectTo: "/servers" });
            }}
          >
            <button className="rounded-lg bg-[#5865F2] px-6 py-3 font-semibold text-white transition hover:opacity-85">
              Sign in with Discord
            </button>
          </form>
        </div>
      </div>
    );
  }

  const token = await userAccessToken();
  const [userGuilds, botGuildIds] = token
    ? await Promise.all([fetchUserGuilds(token), fetchBotGuildIds()])
    : [null, null];

  // Signed in before the guilds scope existed (or the token expired):
  // a fresh sign-in fixes both.
  if (!userGuilds || !botGuildIds) {
    return (
      <div className="mx-auto max-w-md px-4 py-20">
        <div className="flex flex-col items-center gap-4 rounded-xl border border-white/10 bg-white/[0.03] p-10 text-center">
          <h1 className="text-xl font-bold">Please sign in again</h1>
          <p className="text-sm text-foreground/60">
            We need permission to see your server list. Sign out and back in to
            grant it.
          </p>
          <form
            action={async () => {
              "use server";
              await signOut({ redirectTo: "/servers" });
            }}
          >
            <button className="rounded-lg bg-accent px-6 py-3 font-semibold text-white transition hover:opacity-85">
              Sign out
            </button>
          </form>
        </div>
      </div>
    );
  }

  const manageable = userGuilds.filter((g) => g.canManage && botGuildIds.has(g.id));

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <h1 className="text-3xl font-bold tracking-tight">Your servers</h1>
      <p className="mt-2 text-foreground/60">
        Servers with TrabajoBot where you can manage commands.
      </p>

      {manageable.length === 0 ? (
        <div className="mt-10 rounded-xl border border-white/10 bg-white/[0.03] p-8 text-center text-foreground/60">
          No manageable servers found. You need Manage Server permission in a
          server that has TrabajoBot.
        </div>
      ) : (
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {manageable.map((g) => (
            <Link
              key={g.id}
              href={`/servers/${g.id}`}
              className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-4 transition hover:border-accent/40"
            >
              {g.icon ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={`https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png?size=64`}
                  alt=""
                  className="h-10 w-10 rounded-full"
                />
              ) : (
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-accent/30 font-semibold">
                  {g.name[0]}
                </div>
              )}
              <span className="truncate font-medium">{g.name}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
