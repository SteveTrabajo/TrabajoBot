# TrabajoBot Website

Public site for TrabajoBot: landing page, live command list, and (coming soon)
a client dashboard and admin panel.

## Stack

Next.js (App Router, TypeScript) + Tailwind CSS. The `/commands` page fetches
the bot's registered slash commands from Discord's API at render time
(revalidated hourly), so it never needs manual updates.

## Local development

```bash
cd web
cp .env.example .env.local   # fill in DISCORD_BOT_TOKEN
npm install
npm run dev
```

Without the env vars the site still runs; `/commands` shows an
"unavailable" notice instead of the command list.

## Deploying to Vercel

1. Push this repo to GitHub.
2. In [Vercel](https://vercel.com/new), import the repo.
3. Set **Root Directory** to `web/` (Framework Preset: Next.js is auto-detected).
4. Add the environment variables from `.env.example`.
5. Deploy. Every push to `main` that touches `web/` redeploys automatically.
