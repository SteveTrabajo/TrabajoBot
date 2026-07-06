import NextAuth from "next-auth";
import Discord from "next-auth/providers/discord";

// clientSecret comes from AUTH_DISCORD_SECRET automatically; the app id is
// shared with the commands-page fetch, hence the explicit non-AUTH_ name.
export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Discord({
      clientId: process.env.DISCORD_APP_ID,
      // guilds: lets the site list the user's servers for command toggles
      authorization: { params: { scope: "identify guilds" } },
    }),
  ],
  callbacks: {
    jwt({ token, profile, account }) {
      // Persist the Discord snowflake; it's the key for all bot tables.
      if (profile?.id) token.discordId = profile.id;
      if (account?.access_token) token.accessToken = account.access_token;
      return token;
    },
    session({ session, token }) {
      (session.user as { id?: string }).id =
        (token.discordId as string) ?? token.sub!;
      (session as { accessToken?: string }).accessToken =
        token.accessToken as string | undefined;
      return session;
    },
  },
});

/** The logged-in user's Discord id (snowflake), or null when logged out. */
export async function discordUserId(): Promise<string | null> {
  const session = await auth();
  return (session?.user as { id?: string } | undefined)?.id ?? null;
}

/** True when the logged-in user is the bot owner. */
export async function isAdmin(): Promise<boolean> {
  const id = await discordUserId();
  return !!id && !!process.env.ADMIN_DISCORD_ID && id === process.env.ADMIN_DISCORD_ID;
}

/** The user's OAuth access token; null when logged out or on a pre-guilds-scope session. */
export async function userAccessToken(): Promise<string | null> {
  const session = await auth();
  return (session as { accessToken?: string } | null)?.accessToken ?? null;
}
