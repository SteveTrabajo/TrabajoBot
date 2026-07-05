import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { INVITE_URL } from "@/lib/discord";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "TrabajoBot",
  description:
    "A Discord bot with the monthly pickle game, birthdays, moderation and more.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-screen flex flex-col font-sans">
        <header className="sticky top-0 z-10 border-b border-white/10 bg-background/80 backdrop-blur">
          <nav className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
            <Link href="/" className="text-lg font-bold tracking-tight">
              Trabajo<span className="text-accent">Bot</span>
            </Link>
            <div className="flex items-center gap-2 sm:gap-4">
              <Link
                href="/commands"
                className="rounded-md px-3 py-1.5 text-sm text-foreground/80 transition hover:bg-white/5 hover:text-foreground"
              >
                Commands
              </Link>
              <Link
                href="/dashboard"
                className="rounded-md px-3 py-1.5 text-sm text-foreground/80 transition hover:bg-white/5 hover:text-foreground"
              >
                Dashboard
              </Link>
              <a
                href={INVITE_URL}
                className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white transition hover:opacity-85"
              >
                Add to Discord
              </a>
            </div>
          </nav>
        </header>

        <main className="flex-1">{children}</main>

        <footer className="border-t border-white/10 py-6 text-center text-sm text-foreground/50">
          TrabajoBot, made with 🍆 for friends.
        </footer>
      </body>
    </html>
  );
}
