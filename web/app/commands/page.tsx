import type { Metadata } from "next";
import { fetchCommandCategories } from "@/lib/discord";

export const metadata: Metadata = {
  title: "Commands | TrabajoBot",
  description: "All of TrabajoBot's slash commands.",
};

export default async function CommandsPage() {
  const categories = await fetchCommandCategories();

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <h1 className="text-3xl font-bold tracking-tight">Commands</h1>
      <p className="mt-2 text-foreground/60">
        Fetched straight from Discord, so it&apos;s always up to date.
      </p>

      {categories === null ? (
        <div className="mt-10 rounded-xl border border-white/10 bg-white/[0.03] p-8 text-center text-foreground/60">
          The command list is unavailable right now. Try again in a bit.
        </div>
      ) : (
        <div className="mt-10 space-y-10">
          {categories.map((category) => (
            <section key={category.name}>
              <h2 className="mb-4 text-xl font-semibold">
                <span className="mr-2">{category.emoji}</span>
                {category.name}
              </h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {category.commands.map((cmd) => (
                  <div
                    key={cmd.name}
                    className="rounded-lg border border-white/10 bg-white/[0.03] p-4"
                  >
                    <code className="font-mono text-sm font-semibold text-accent">
                      /{cmd.name}
                    </code>
                    <p className="mt-1 text-sm text-foreground/60">
                      {cmd.description}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
