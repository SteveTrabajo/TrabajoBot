"use client";
import { useState, useTransition } from "react";
import { setCommands } from "./actions";
import type { CommandCategory } from "@/lib/discord";

function Switch({
  on,
  onClick,
  disabled,
}: {
  on: boolean;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      disabled={disabled}
      onClick={onClick}
      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50 ${
        on ? "bg-accent" : "bg-white/15"
      }`}
    >
      <span
        className={`absolute left-0 top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
          on ? "translate-x-5.5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

export default function ToggleBoard({
  guildId,
  categories,
  initialDisabled,
}: {
  guildId: string;
  categories: CommandCategory[];
  initialDisabled: string[];
}) {
  const [disabled, setDisabled] = useState(new Set(initialDisabled));
  const [pending, startTransition] = useTransition();

  function apply(commands: string[], enabled: boolean) {
    // Optimistic: flip locally, revert if the server says no.
    const prev = new Set(disabled);
    const next = new Set(disabled);
    for (const c of commands) (enabled ? next.delete(c) : next.add(c));
    setDisabled(next);
    startTransition(async () => {
      const res = await setCommands(guildId, commands, enabled).catch(() => ({ ok: false }));
      if (!res.ok) setDisabled(prev);
    });
  }

  return (
    <div className="space-y-4">
      {categories.map((cat) => {
        const names = cat.commands.map((c) => c.name);
        const anyEnabled = names.some((n) => !disabled.has(n));
        return (
          <section
            key={cat.name}
            className="rounded-xl border border-white/10 bg-white/[0.03] p-5"
          >
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-semibold">
                <span className="mr-2">{cat.emoji}</span>
                {cat.name}
              </h2>
              <Switch
                on={anyEnabled}
                disabled={pending}
                onClick={() => apply(names, !anyEnabled)}
              />
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {cat.commands.map((cmd) => {
                const on = !disabled.has(cmd.name);
                return (
                  <div
                    key={cmd.name}
                    className={`flex items-center justify-between gap-3 rounded-lg border border-white/10 p-3 transition-opacity ${
                      on ? "" : "opacity-50"
                    }`}
                  >
                    <div className="min-w-0">
                      <code className="text-sm font-semibold text-accent">
                        /{cmd.name}
                      </code>
                      <p className="truncate text-xs text-foreground/50">
                        {cmd.description}
                      </p>
                    </div>
                    <Switch
                      on={on}
                      disabled={pending}
                      onClick={() => apply([cmd.name], !on)}
                    />
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
