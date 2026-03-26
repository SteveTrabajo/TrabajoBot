# TrabajoBot 🤖

> A feature-rich Discord bot built with Python and discord.py, bringing moderation, music, fun, and utility commands to your server.

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![discord.py](https://img.shields.io/badge/discord.py-latest-5865F2.svg)](https://discordpy.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🚀 Features

| Category | Description |
|---|---|
| 🛡️ **Moderation** | Kick, ban, and unban members with optional reasons |
| ℹ️ **Information** | User info, server info, and ping |
| 🎉 **Fun** | Magic 8-ball, coin flip, and pew-pew GIFs |
| 🎵 **Music** | Play, skip, pause/resume, volume control, and audio filters via Wavelink |
| 🎂 **Birthdays** | Set, view, and list server members' birthdays (stored in CockroachDB) |
| 🍆 **Pickle Game** | A leaderboard-based size-tracking game with growth graphs |
| ❓ **Help** | Category-aware slash command help with autocomplete |

All commands are implemented as **Discord Slash Commands** (Application Commands API).

---

## 🛠️ Tech Stack

- **Language:** Python 3.8+
- **Library:** [discord.py](https://github.com/Rapptz/discord.py)
- **Database:** PostgreSQL via [CockroachDB](https://www.cockroachlabs.com/)
- **Hosting:** PebbleHost

---

## 📥 Getting Started

### Prerequisites

- Python 3.8 or higher
- A Discord bot application and token ([Discord Developer Portal](https://discord.com/developers/applications))
- Git

### Installation

```bash
git clone https://github.com/SteveTrabajo/TrabajoBot.git
cd TrabajoBot

python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
# Required
DISCORD_BOT_TOKEN=your_bot_token_here

# Database (CockroachDB / PostgreSQL)
DB_HOST=your_db_host
DB_USER=your_db_user
DB_PASS=your_db_password
DB_NAME=your_db_name
DB_PORT=26257

# Optional — fun commands
GIPHY_API_KEY=your_giphy_api_key
```

### Run

```bash
python main.py
```

---

## 💬 Slash Commands

### 🛡️ Moderation
| Command | Description | Required Permission |
|---|---|---|
| `/kick <member> [reason]` | Kick a member from the server | Kick Members |
| `/ban <member> [reason]` | Ban a member from the server | Ban Members |
| `/unban <username>` | Unban a user by username | Ban Members |

### ℹ️ Information
| Command | Description |
|---|---|
| `/ping` | Shows the bot's current latency |
| `/userinfo [member]` | Displays account info, roles, and status for a user |
| `/serverinfo` | Displays server stats (members, boosts, channels, etc.) |
| `/invite` | Sends a button to invite TrabajoBot to another server |

### 🎉 Fun
| Command | Description |
|---|---|
| `/8ball <question>` | Ask the magic 8-ball a question |
| `/coin [member]` | Flip a coin (optionally challenge another member) |
| `/pew <member>` | Shoot a member with a random GIF |

### 🎵 Music *(not working, currently under re-work)*
| Command | Description |
|---|---|
| `/play <query>` | Play a song or playlist by name or URL |
| `/skip` | Skip the current track |
| `/toggle` | Pause or resume the player |
| `/volume <value>` | Set the playback volume |
| `/nightcore` | Apply a nightcore audio filter |
| `/resetfilters` | Reset all audio filters |
| `/disconnect` | Disconnect the bot from the voice channel |

### 🎂 Birthdays
| Command | Description |
|---|---|
| `/setbirthday <YYYY-MM-DD>` | Save your birthday |
| `/mybirthday` | View your stored birthday |
| `/birthdaylist` | List all birthdays for members in this server |

### ❓ Help
| Command | Description |
|---|---|
| `/help [category]` | Show all command categories, or commands for a specific category |

---

## 🎯 Invite

[**Click here to invite TrabajoBot**](https://discord.com/oauth2/authorize?client_id=1000039115183640588)

---

## 🤝 Contributing

Contributions are welcome! To get started:

1. Fork this repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "Add your feature"`
4. Push to your branch: `git push origin feature/your-feature`
5. Open a Pull Request describing your changes

Please follow the existing code style and include comments where necessary.

---

## 📝 License

This project is licensed under the [MIT License](LICENSE).
