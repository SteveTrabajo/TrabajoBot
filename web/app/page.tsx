import Link from "next/link";
import { INVITE_URL } from "@/lib/discord";

const FEATURES = [
  {
    emoji: "🍆",
    title: "The Pickle Game",
    description:
      "Roll your monthly pickle size, climb the server and global leaderboards, and track your growth over the year with graphs.",
  },
  {
    emoji: "🎂",
    title: "Birthdays",
    description:
      "Save your birthday and browse everyone else's, so the server never misses a celebration.",
  },
  {
    emoji: "🎉",
    title: "Fun Commands",
    description:
      "Ask the magic 8-ball, flip coins against your friends, and pew-pew people with random GIFs.",
  },
  {
    emoji: "🛡️",
    title: "Moderation",
    description:
      "Kick, ban and unban with proper permission checks. The essentials, no bloat.",
  },
];

export default function Home() {
  return (
    <div className="mx-auto max-w-5xl px-4">
      {/* Hero */}
      <section className="flex flex-col items-center gap-6 py-20 text-center sm:py-28">
        <h1 className="max-w-2xl text-4xl font-extrabold tracking-tight sm:text-6xl">
          The bot your server{" "}
          <span className="bg-gradient-to-r from-accent to-fuchsia-400 bg-clip-text text-transparent">
            didn&apos;t know it needed
          </span>
        </h1>
        <p className="max-w-xl text-lg text-foreground/70">
          Monthly pickle rankings, birthday tracking, moderation tools and fun
          commands, all in one bot.
        </p>
        <div className="flex flex-col gap-3 sm:flex-row">
          <a
            href={INVITE_URL}
            className="rounded-lg bg-accent px-6 py-3 font-semibold text-white transition hover:opacity-85"
          >
            Add to Discord
          </a>
          <Link
            href="/commands"
            className="rounded-lg border border-white/15 px-6 py-3 font-semibold transition hover:bg-white/5"
          >
            Browse commands
          </Link>
        </div>
      </section>

      {/* Features */}
      <section className="grid gap-4 pb-20 sm:grid-cols-2">
        {FEATURES.map((feature) => (
          <div
            key={feature.title}
            className="rounded-xl border border-white/10 bg-white/[0.03] p-6 transition hover:border-accent/40"
          >
            <div className="mb-3 text-3xl">{feature.emoji}</div>
            <h2 className="mb-1 text-lg font-semibold">{feature.title}</h2>
            <p className="text-sm leading-relaxed text-foreground/60">
              {feature.description}
            </p>
          </div>
        ))}
      </section>
    </div>
  );
}
