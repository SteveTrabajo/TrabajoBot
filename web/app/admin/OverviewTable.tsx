"use client";
import Link from "next/link";
import { useState } from "react";

export interface OverviewRow {
  user_id: string;
  name: string;
  current_size: number | null;
  last_month: string;
  entries: number;
}

const PAGE_SIZE = 10;

export default function OverviewTable({ rows }: { rows: OverviewRow[] }) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);

  const q = search.trim().toLowerCase();
  const filtered = q
    ? rows.filter(
        (r) => r.name.toLowerCase().includes(q) || r.user_id.includes(q)
      )
    : rows;
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, pages - 1);
  const visible = filtered.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE);

  return (
    <div className="mt-4">
      <input
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(0);
        }}
        placeholder="Search by name or ID…"
        className="mb-3 w-full max-w-xs rounded-md border border-white/15 bg-transparent px-3 py-1.5 text-sm [color-scheme:dark]"
      />
      <div className="overflow-x-auto">
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
            {visible.map((row) => (
              <tr key={row.user_id} className="border-b border-white/5">
                <td className="py-2 pr-4">
                  <span className="font-medium">{row.name}</span>{" "}
                  <code className="text-xs text-foreground/40">{row.user_id}</code>
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
                  <Link
                    href={`/admin?user=${row.user_id}`}
                    className="rounded-md bg-accent px-3 py-1 text-sm font-medium text-white transition hover:opacity-85"
                  >
                    View history
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length === 0 && (
        <p className="mt-2 text-sm text-foreground/50">No users match.</p>
      )}
      {pages > 1 && (
        <div className="mt-3 flex items-center gap-3 text-sm">
          <button
            onClick={() => setPage(current - 1)}
            disabled={current === 0}
            className="rounded-md border border-white/15 px-3 py-1 disabled:opacity-30"
          >
            ◀
          </button>
          <span className="text-foreground/60">
            {current + 1} / {pages}
          </span>
          <button
            onClick={() => setPage(current + 1)}
            disabled={current >= pages - 1}
            className="rounded-md border border-white/15 px-3 py-1 disabled:opacity-30"
          >
            ▶
          </button>
        </div>
      )}
    </div>
  );
}
