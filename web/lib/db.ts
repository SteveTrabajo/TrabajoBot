import { Pool } from "pg";

// One pool per process; stashed on globalThis so dev hot-reload doesn't
// open a new pool on every file change. Small max: serverless functions
// are many and short-lived, CockroachDB connections are not free.
const globalForDb = globalThis as unknown as { pgPool?: Pool };

const pool =
  globalForDb.pgPool ??
  new Pool({ connectionString: process.env.DATABASE_URL, max: 3 });
globalForDb.pgPool = pool;

export async function query<T = Record<string, unknown>>(
  text: string,
  params?: unknown[]
): Promise<T[]> {
  const res = await pool.query(text, params);
  return res.rows as T[];
}
