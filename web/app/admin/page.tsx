import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { revalidatePath } from "next/cache";
import { isAdmin } from "@/auth";
import { query } from "@/lib/db";
import SizeField from "./SizeField";

export const metadata: Metadata = {
  title: "Admin | TrabajoBot",
};

// ---------- helpers ----------

const isSnowflake = (v: unknown): v is string =>
  typeof v === "string" && /^\d{5,25}$/.test(v);
const isDate = (v: unknown): v is string =>
  typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v) && !isNaN(Date.parse(v));
const isMonth = (v: unknown): v is string =>
  typeof v === "string" && /^\d{4}-\d{2}$/.test(v);
const parseSize = (v: unknown): number | null => {
  const n = Number(v);
  return Number.isInteger(n) && n >= 0 && n <= 999 ? n : null;
};
// UTC, matching the bot's month_key convention.
const currentMonth = () => new Date().toISOString().slice(0, 7);

/**
 * Recompute a user's current size from their latest history row of the
 * current month, so history edits and the /pickle state never disagree.
 */
async function syncCurrentSize(userId: string) {
  const rows = await query<{ size: number }>(
    `SELECT size::int4 AS size FROM pickle_history
     WHERE user_id = $1 AND to_char(recorded_at, 'YYYY-MM') = $2
     ORDER BY recorded_at DESC LIMIT 1`,
    [userId, currentMonth()]
  );
  if (rows.length > 0) {
    await query(
      `INSERT INTO pickle_sizes (user_id, current_size) VALUES ($1, $2)
       ON CONFLICT (user_id) DO UPDATE SET current_size = $2, last_updated = CURRENT_TIMESTAMP`,
      [userId, rows[0].size]
    );
  } else {
    await query("DELETE FROM pickle_sizes WHERE user_id = $1", [userId]);
  }
}

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
  // Keep this month's history row in step so the graph agrees.
  const updated = await query(
    `UPDATE pickle_history SET size = $2
     WHERE user_id = $1 AND to_char(recorded_at, 'YYYY-MM') = $3 RETURNING 1`,
    [userId, size, currentMonth()]
  );
  if (updated.length === 0) {
    await query("INSERT INTO pickle_history (user_id, size) VALUES ($1, $2)", [
      userId,
      size,
    ]);
  }
  revalidatePath("/admin");
}

async function deleteSize(formData: FormData) {
  "use server";
  if (!(await isAdmin())) return;
  const userId = formData.get("user_id");
  if (!isSnowflake(userId)) return;
  await query("DELETE FROM pickle_sizes WHERE user_id = $1", [userId]);
  // Deleting "this month's size" also means removing its history record.
  await query(
    "DELETE FROM pickle_history WHERE user_id = $1 AND to_char(recorded_at, 'YYYY-MM') = $2",
    [userId, currentMonth()]
  );
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
  if (recordedAt.slice(0, 7) === currentMonth()) await syncCurrentSize(userId);
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
  if (recordedAt.slice(0, 7) === currentMonth()) await syncCurrentSize(userId);
  revalidatePath("/admin");
}

async function addHistory(formData: FormData) {
  "use server";
  if (!(await isAdmin())) return;
  const userId = formData.get("user_id");
  const month = formData.get("month");
  const size = parseSize(formData.get("size"));
  if (!isSnowflake(userId) || !isMonth(month) || size === null) return;
  // Sizes are monthly; the stored day is just the 1st as a placeholder.
  await query(
    "INSERT INTO pickle_history (user_id, size, recorded_at) VALUES ($1, $2, $3::timestamp)",
    [userId, size, `${month}-01`]
  );
  if (month === currentMonth()) await syncCurrentSize(userId);
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

  const viewingUser = isSnowflake(historyUser) ? historyUser : null;

  const history = viewingUser
    ? await query<{ recorded_at: string; month: string; day: string; size: number }>(
        `SELECT recorded_at::text AS recorded_at,
                to_char(recorded_at, 'YYYY-MM') AS month,
                recorded_at::date::text AS day,
                size::int4 AS size
         FROM pickle_history WHERE user_id = $1 ORDER BY recorded_at DESC`,
        [viewingUser]
      )
    : null;

  // Overview shown when no user is selected: everyone who ever rolled.
  const overview = viewingUser
    ? []
    : await query<{
        user_id: string;
        current_size: number | null;
        last_month: string;
        entries: number;
      }>(
        `SELECT h.user_id::text AS user_id,
                s.current_size::int4 AS current_size,
                to_char(max(h.recorded_at), 'YYYY-MM') AS last_month,
                count(*)::int4 AS entries
         FROM pickle_history h
         LEFT JOIN pickle_sizes s ON s.user_id = h.user_id
         GROUP BY h.user_id, s.current_size
         ORDER BY max(h.recorded_at) DESC`
      );

  const names = new Map<string, string>();
  await Promise.all(
    [
      ...new Set([
        ...sizes.map((r) => r.user_id),
        ...birthdays.map((r) => r.user_id),
        ...overview.map((r) => r.user_id),
        ...(viewingUser ? [viewingUser] : []),
      ]),
    ].map(async (id) => names.set(id, await username(id)))
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
                <SizeField defaultValue={row.current_size} />
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
          <input name="user" placeholder="User ID (empty for all users)" defaultValue={historyUser ?? ""} className={`${input} w-56`} />
          <button className={btn}>Load history</button>
        </form>

        {!viewingUser && (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-foreground/50">
                  <th className="py-2 pr-4 font-medium">User</th>
                  <th className="py-2 pr-4 font-medium">Current size</th>
                  <th className="py-2 pr-4 font-medium">Last rolled</th>
                  <th className="py-2 pr-4 font-medium">Records</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody>
                {overview.map((row) => (
                  <tr key={row.user_id} className="border-b border-white/5">
                    <td className="py-2 pr-4">
                      <UserLabel id={row.user_id} name={names.get(row.user_id) ?? "?"} />
                    </td>
                    <td className="py-2 pr-4">
                      {row.current_size !== null ? (
                        `${row.current_size} cm`
                      ) : (
                        <span className="text-foreground/40">not rolled</span>
                      )}
                    </td>
                    <td className="py-2 pr-4">{row.last_month}</td>
                    <td className="py-2 pr-4">{row.entries}</td>
                    <td className="py-2 text-right">
                      <a href={`/admin?user=${row.user_id}`} className={btn}>
                        View history
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {overview.length === 0 && (
              <p className="mt-2 text-sm text-foreground/50">No history recorded yet.</p>
            )}
          </div>
        )}

        {viewingUser && (
          <p className="mt-4 text-sm text-foreground/60">
            Viewing{" "}
            <UserLabel id={viewingUser} name={names.get(viewingUser) ?? "?"} />{" "}
            <a href="/admin" className="text-accent underline">
              back to all users
            </a>
          </p>
        )}

        {history && (
          <>
            <div className="mt-4 space-y-2">
              {history.length === 0 && (
                <p className="text-sm text-foreground/50">No history for this user.</p>
              )}
              {history.map((row, i) => {
                const dupe =
                  history.some((o, j) => j !== i && o.month === row.month);
                return (
                <div key={row.recorded_at} className="flex flex-wrap items-center gap-2">
                  <code className="text-sm text-foreground/60">
                    {row.month}
                    {dupe && (
                      <span className="ml-1 text-xs text-red-400">
                        (duplicate, {row.day})
                      </span>
                    )}
                  </code>
                  <form action={updateHistory} className="ml-auto flex items-center gap-2">
                    <input type="hidden" name="user_id" value={historyUser} />
                    <input type="hidden" name="recorded_at" value={row.recorded_at} />
                    <SizeField defaultValue={row.size} />
                  </form>
                  <form action={deleteHistory}>
                    <input type="hidden" name="user_id" value={historyUser} />
                    <input type="hidden" name="recorded_at" value={row.recorded_at} />
                    <button className={btnDanger}>Delete</button>
                  </form>
                </div>
                );
              })}
            </div>
            <form action={addHistory} className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/10 pt-4">
              <input type="hidden" name="user_id" value={historyUser} />
              <input type="month" name="month" required className={input} />
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
