import type { Metadata } from "next";
import Link from "next/link";
import { revalidatePath } from "next/cache";
import { auth, signIn, signOut, discordUserId, isAdmin } from "@/auth";
import { query } from "@/lib/db";

export const metadata: Metadata = {
  title: "Dashboard | TrabajoBot",
};

async function getPickleSize(userId: string): Promise<number | null> {
  // ::int4 because CockroachDB INTs are int8, which pg returns as strings.
  const rows = await query<{ current_size: number }>(
    "SELECT current_size::int4 AS current_size FROM pickle_sizes WHERE user_id = $1",
    [userId]
  );
  return rows[0]?.current_size ?? null;
}

async function getPickleHistory(userId: string) {
  return query<{ month: string; size: number }>(
    `SELECT to_char(recorded_at, 'Mon ''YY') AS month, size::int4 AS size
     FROM pickle_history
     WHERE user_id = $1 AND recorded_at > NOW() - INTERVAL '12 months'
     ORDER BY recorded_at ASC`,
    [userId]
  );
}

async function getBirthday(userId: string): Promise<string | null> {
  const rows = await query<{ birthday: string }>(
    "SELECT birthday_date::text AS birthday FROM birthdays WHERE user_id = $1",
    [userId]
  );
  return rows[0]?.birthday ?? null;
}

async function saveBirthday(formData: FormData) {
  "use server";
  const userId = await discordUserId();
  if (!userId) return;

  const date = formData.get("birthday");
  // Trust boundary: validate even though the input is type=date.
  if (
    typeof date !== "string" ||
    !/^\d{4}-\d{2}-\d{2}$/.test(date) ||
    isNaN(Date.parse(date)) ||
    date < "1900-01-01" ||
    date > new Date().toISOString().slice(0, 10)
  ) {
    return;
  }

  await query(
    `INSERT INTO birthdays (user_id, birthday_date) VALUES ($1, $2)
     ON CONFLICT (user_id) DO UPDATE SET birthday_date = EXCLUDED.birthday_date`,
    [userId, date]
  );
  revalidatePath("/dashboard");
}

function SignInCard() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 rounded-xl border border-white/10 bg-white/[0.03] p-10 text-center">
      <h1 className="text-2xl font-bold">Your TrabajoBot data</h1>
      <p className="text-sm text-foreground/60">
        Sign in with Discord to see your pickle stats and manage your birthday.
      </p>
      <form
        action={async () => {
          "use server";
          await signIn("discord", { redirectTo: "/dashboard" });
        }}
      >
        <button className="rounded-lg bg-[#5865F2] px-6 py-3 font-semibold text-white transition hover:opacity-85">
          Sign in with Discord
        </button>
      </form>
    </div>
  );
}

function HistoryChart({ history }: { history: { month: string; size: number }[] }) {
  if (history.length === 0) {
    return (
      <p className="text-sm text-foreground/60">
        No history yet. Use <code className="text-accent">/pickle</code> in
        Discord to get started.
      </p>
    );
  }
  const max = Math.max(...history.map((h) => h.size));
  const BAR_MAX_PX = 144; // pixel heights: % would resolve against auto-height columns
  return (
    <div className="flex items-end gap-2">
      {history.map((h, i) => (
        <div key={i} className="flex flex-1 flex-col items-center gap-1">
          <span className="text-xs text-foreground/70">{h.size}</span>
          <div
            className={`w-full rounded-t ${h.size === max ? "bg-accent" : "bg-white/30"}`}
            style={{ height: `${Math.max(Math.round((h.size / max) * BAR_MAX_PX), 4)}px` }}
          />
          <span className="text-xs text-foreground/50">{h.month}</span>
        </div>
      ))}
    </div>
  );
}

export default async function DashboardPage() {
  const session = await auth();
  const userId = (session?.user as { id?: string } | undefined)?.id;

  if (!session?.user || !userId) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-20">
        <SignInCard />
      </div>
    );
  }

  const [size, history, birthday, admin] = await Promise.all([
    getPickleSize(userId),
    getPickleHistory(userId),
    getBirthday(userId),
    isAdmin(),
  ]);

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">
          Hey, {session.user.name} 👋
        </h1>
        <div className="flex items-center gap-2">
          {admin && (
            <Link
              href="/admin"
              className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white transition hover:opacity-85"
            >
              Admin panel
            </Link>
          )}
          <form
            action={async () => {
              "use server";
              await signOut({ redirectTo: "/" });
            }}
          >
            <button className="rounded-md border border-white/15 px-3 py-1.5 text-sm text-foreground/70 transition hover:bg-white/5">
              Sign out
            </button>
          </form>
        </div>
      </div>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {/* Current pickle */}
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-6">
          <h2 className="text-sm font-medium text-foreground/60">
            🍆 Current pickle size
          </h2>
          <p className="mt-2 text-4xl font-extrabold">
            {size !== null ? (
              <>
                {size} <span className="text-lg font-normal">cm</span>
              </>
            ) : (
              <span className="text-lg font-normal text-foreground/60">
                Not rolled this month. Use /pickle!
              </span>
            )}
          </p>
        </div>

        {/* Birthday */}
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-6">
          <h2 className="text-sm font-medium text-foreground/60">
            🎂 Your birthday
          </h2>
          <form action={saveBirthday} className="mt-3 flex items-center gap-2">
            <input
              type="date"
              name="birthday"
              defaultValue={birthday ?? ""}
              required
              className="rounded-md border border-white/15 bg-transparent px-3 py-2 text-sm [color-scheme:dark]"
            />
            <button className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition hover:opacity-85">
              Save
            </button>
          </form>
        </div>

        {/* History */}
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-6 sm:col-span-2">
          <h2 className="mb-4 text-sm font-medium text-foreground/60">
            📈 Pickle history (last 12 months)
          </h2>
          <HistoryChart history={history} />
        </div>
      </div>
    </div>
  );
}
