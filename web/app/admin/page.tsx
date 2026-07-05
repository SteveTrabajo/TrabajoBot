import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { revalidatePath } from "next/cache";
import { isAdmin } from "@/auth";
import { query } from "@/lib/db";

export const metadata: Metadata = {
  title: "Admin | TrabajoBot",
};

// ---------- helpers ----------

const isSnowflake = (v: unknown): v is string =>
  typeof v === "string" && /^\d{5,25}$/.test(v);
const isDate = (v: unknown): v is string =>
  typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v) && !isNaN(Date.parse(v));
const parseSize = (v: unknown): number | null => {
  const n = Number(v);
  return Number.isInteger(n) && n >= 0 && n <= 999 ? n : null;
};

/** Resolve a user id to a Discord username; cached for a day. */
async function username(id: string): Promise<string> {
  try {
    const res = await fetch(`https://discord.com/api/v10/users/${id}`, {
      headers: { Authorization: `Bot ${process.env.DISCORD_BOT_TOKEN}` },
      next: { revalidate: 86400 },
    });
    if (!res.ok) return "unknown";
    return (await res.json()).username ?? "unknown";
  } catch {
    return "unknown";
  }
}

// ---------- server actions (every one re-checks admin) ----------

async function upsertSize(formData: FormData) {
  "use server";
  if (!(await isAdmin())) return;
  const userId = formData.get("user_id");
  const size = parseSize(formData.get("size"));
  if (!isSnowflake(userId) || size === null) return;
  await query(
    `INSERT INTO pickle_sizes (user_id, current_size) VALUES ($1, $2)
     ON CONFLICT (user_id) DO UPDATE SET current_size = $2, last_updated = CURRENT_TIMESTAMP`,
    [userId, size]
  );
  revalidatePath("/admin");
}

async function deleteSize(formData: FormData) {
  "use server";
  if (!(await isAdmin())) return;
  const userId = formData.get("user_id");
  if (!isSnowflake(userId)) return;
  await query("DELETE FROM pickle_sizes WHERE user_id = $1", [userId]);
  revalidatePath("/admin");
}

async function updateHistory(formData: FormData) {
  "use server";
  if (!(await isAdmin())) return;
  const userId = formData.get("user_id");
  const recordedAt = formData.get("recorded_at");
  const size = parseSize(formData.get("size"));
  if (!isSnowflake(userId) || typeof recordedAt !== "string" || size === null) return;
  await query(
    "UPDATE pickle_history SET size = $3 WHERE user_id = $1 AND recorded_at = $2::timestamp",
    [userId, recordedAt, size]
  );
  revalidatePath("/admin");
}

async function deleteHistory(formData: FormData) {
  "use server";
  if (!(await isAdmin())) return;
  const userId = formData.get("user_id");
  const recordedAt = formData.get("recorded_at");
  if (!isSnowflake(userId) || typeof recordedAt !== "string") return;
  await query(
    "DELETE FROM pickle_history WHERE user_id = $1 AND recorded_at = $2::timestamp",
    [userId, recordedAt]
  );
  revalidatePath("/admin");
}

async function addHistory(formData: FormData) {
  "use server";
  if (!(await isAdmin())) return;
  const userId = formData.get("user_id");
  const date = formData.get("date");
  const size = parseSize(formData.get("size"));
  if (!isSnowflake(userId) || !isDate(date) || size === null) return;
  await query(
    "INSERT INTO pickle_history (user_id, size, recorded_at) VALUES ($1, $2, $3::timestamp)",
    [userId, size, date]
  );
  revalidatePath("/admin");
}

async function upsertBirthday(formData: FormData) {
  "use server";
  if (!(await isAdmin())) return;
  const userId = formData.get("user_id");
  const date = formData.get("birthday");
  if (!isSnowflake(userId) || !isDate(date)) return;
  await query(
    `INSERT INTO birthdays (user_id, birthday_date) VALUES ($1, $2)
     ON CONFLICT (user_id) DO UPDATE SET birthday_date = EXCLUDED.birthday_date`,
    [userId, date]
  );
  revalidatePath("/admin");
}

async function deleteBirthday(formData: FormData) {
  "use server";
  if (!(await isAdmin())) return;
  const userId = formData.get("user_id");
  if (!isSnowflake(userId)) return;
  await query("DELETE FROM birthdays WHERE user_id = $1", [userId]);
  revalidatePath("/admin");
}

async function saveRollover(formData: FormData) {
  "use server";
  if (!(await isAdmin())) return;
  const value = formData.get("value");
  if (typeof value !== "string" || !/^\d{4}-\d{2}$/.test(value)) return;
  await query(
    `INSERT INTO pickle_meta (key, value) VALUES ('last_rollover', $1)
     ON CONFLICT (key) DO UPDATE SET value = $1`,
    [value]
  );
  revalidatePath("/admin");
}

// ---------- UI bits ----------

const card = "rounded-xl border border-white/10 bg-white/[0.03] p-6";
const input =
  "rounded-md border border-white/15 bg-transparent px-2 py-1 text-sm [color-scheme:dark]";
const btn =
  "rounded-md bg-accent px-3 py-1 text-sm font-medium text-white transition hover:opacity-85";
const btnDanger =
  "rounded-md border border-red-500/40 px-3 py-1 text-sm text-red-400 transition hover:bg-red-500/10";

function UserLabel({ id, name }: { id: string; name: string }) {
  return (
    <span className="min-w-0">
      <span className="font-medium">{name}</span>{" "}
      <code className="text-xs text-foreground/40">{id}</code>
    </span>
  );
}

// ---------- page ----------

export default async function AdminPage({
  searchParams,
}: {
  searchParams: Promise<{ user?: string }>;
}) {
  if (!(await isAdmin())) notFound();

  const { user: historyUser } = await searchParams;

  const [sizes, birthdays, meta] = await Promise.all([
    query<{ user_id: string; current_size: number; last_updated: string }>(
      "SELECT user_id::text AS user_id, current_size::int4 AS current_size, last_updated::text AS last_updated FROM pickle_sizes ORDER BY current_size DESC"
    ),
    query<{ user_id: string; birthday: string }>(
      "SELECT user_id::text AS user_id, birthday_date::text AS birthday FROM birthdays ORDER BY birthday_date"
    ),
    query<{ value: string }>(
      "SELECT value FROM pickle_meta WHERE key = 'last_rollover'"
    ),
  ]);

  const history = isSnowflake(historyUser)
    ? await query<{ recorded_at: string; day: string; size: number }>(
        `SELECT recorded_at::text AS recorded_at, recorded_at::date::text AS day, size::int4 AS size
         FROM pickle_history WHERE user_id = $1 ORDER BY recorded_at DESC`,
        [historyUser]
      )
    : null;

  const names = new Map<string, string>();
  await Promise.all(
    [...new Set([...sizes, ...birthdays].map((r) => r.user_id))].map(
      async (id) => names.set(id, await username(id))
    )
  );

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-12">
      <h1 className="text-3xl font-bold tracking-tight">Admin panel</h1>

      {/* Current pickle sizes */}
      <section className={card}>
        <h2 className="mb-4 text-lg font-semibold">🍆 Current pickle sizes</h2>
        <div className="space-y-2">
          {sizes.length === 0 && (
            <p className="text-sm text-foreground/50">No sizes this month.</p>
          )}
          {sizes.map((row) => (
            <div key={row.user_id} className="flex flex-wrap items-center gap-2">
              <UserLabel id={row.user_id} name={names.get(row.user_id) ?? "?"} />
              <form action={upsertSize} className="ml-auto flex items-center gap-2">
                <input type="hidden" name="user_id" value={row.user_id} />
                <input type="number" name="size" defaultValue={row.current_size} min={0} max={999} className={`${input} w-20`} />
                <button className={btn}>Save</button>
              </form>
              <form action={deleteSize}>
                <input type="hidden" name="user_id" value={row.user_id} />
                <button className={btnDanger}>Delete</button>
              </form>
            </div>
          ))}
        </div>
        <form action={upsertSize} className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/10 pt-4">
          <input name="user_id" placeholder="User ID" required className={`${input} w-48`} />
          <input type="number" name="size" placeholder="cm" min={0} max={999} required className={`${input} w-20`} />
          <button className={btn}>Add / set</button>
        </form>
      </section>

      {/* History editor */}
      <section className={card}>
        <h2 className="mb-4 text-lg font-semibold">📈 Pickle history</h2>
        <form method="GET" className="flex flex-wrap items-center gap-2">
          <input name="user" placeholder="User ID" defaultValue={historyUser ?? ""} required className={`${input} w-48`} />
          <button className={btn}>Load history</button>
        </form>

        {history && (
          <>
            <div className="mt-4 space-y-2">
              {history.length === 0 && (
                <p className="text-sm text-foreground/50">No history for this user.</p>
              )}
              {history.map((row) => (
                <div key={row.recorded_at} className="flex flex-wrap items-center gap-2">
                  <code className="text-sm text-foreground/60">{row.day}</code>
                  <form action={updateHistory} className="ml-auto flex items-center gap-2">
                    <input type="hidden" name="user_id" value={historyUser} />
                    <input type="hidden" name="recorded_at" value={row.recorded_at} />
                    <input type="number" name="size" defaultValue={row.size} min={0} max={999} className={`${input} w-20`} />
                    <button className={btn}>Save</button>
                  </form>
                  <form action={deleteHistory}>
                    <input type="hidden" name="user_id" value={historyUser} />
                    <input type="hidden" name="recorded_at" value={row.recorded_at} />
                    <button className={btnDanger}>Delete</button>
                  </form>
                </div>
              ))}
            </div>
            <form action={addHistory} className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/10 pt-4">
              <input type="hidden" name="user_id" value={historyUser} />
              <input type="date" name="date" required className={input} />
              <input type="number" name="size" placeholder="cm" min={0} max={999} required className={`${input} w-20`} />
              <button className={btn}>Add record</button>
            </form>
          </>
        )}
      </section>

      {/* Birthdays */}
      <section className={card}>
        <h2 className="mb-4 text-lg font-semibold">🎂 Birthdays</h2>
        <div className="space-y-2">
          {birthdays.length === 0 && (
            <p className="text-sm text-foreground/50">No birthdays stored.</p>
          )}
          {birthdays.map((row) => (
            <div key={row.user_id} className="flex flex-wrap items-center gap-2">
              <UserLabel id={row.user_id} name={names.get(row.user_id) ?? "?"} />
              <form action={upsertBirthday} className="ml-auto flex items-center gap-2">
                <input type="hidden" name="user_id" value={row.user_id} />
                <input type="date" name="birthday" defaultValue={row.birthday} className={input} />
                <button className={btn}>Save</button>
              </form>
              <form action={deleteBirthday}>
                <input type="hidden" name="user_id" value={row.user_id} />
                <button className={btnDanger}>Delete</button>
              </form>
            </div>
          ))}
        </div>
        <form action={upsertBirthday} className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/10 pt-4">
          <input name="user_id" placeholder="User ID" required className={`${input} w-48`} />
          <input type="date" name="birthday" required className={input} />
          <button className={btn}>Add / set</button>
        </form>
      </section>

      {/* Rollover marker */}
      <section className={card}>
        <h2 className="mb-2 text-lg font-semibold">⚙️ Monthly rollover marker</h2>
        <p className="mb-4 text-sm text-foreground/50">
          The bot resets pickle sizes once per month and records the month here
          (YYYY-MM). Setting it to a past month makes the next daily check run
          the rollover again; setting it to the current month suppresses it.
        </p>
        <form action={saveRollover} className="flex flex-wrap items-center gap-2">
          <input
            name="value"
            defaultValue={meta[0]?.value ?? ""}
            placeholder="YYYY-MM"
            pattern="\d{4}-\d{2}"
            required
            className={`${input} w-32`}
          />
          <button className={btn}>Save</button>
        </form>
      </section>
    </div>
  );
}
