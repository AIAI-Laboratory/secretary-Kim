# Secretary Kim - Discord Music Bot

A premium, feature-rich Discord music bot built using Python, `discord.py`, `yt-dlp`, and Dependency Injection (`dependency-injector`). It supports playing audio directly from YouTube URLs or search queries, server-specific queues, track looping, and full playback controls via Discord Slash Commands.

---

## Features

- **Slash Commands**: Fully integrated with Discord's modern `/` commands interface.
- **Smart Queuing**: Unique music queues for each Discord server (Guild) running concurrently.
- **Direct Streaming**: Streams directly from YouTube audio streams without wasting disk space.
- **URL Refreshing**: Automatically refreshes YouTube streaming links before playing to prevent link expiration issues.
- **Rich Embeds**: Beautiful feedback messages displaying the title, channel/uploader, duration, thumbnail, and requester.
- **Interactive Control Commands**: `/play`, `/pause`, `/resume`, `/skip`, `/loop`, `/queue`, `/stop`, and `/leave`.

---

## Command List

| Command | Description | Arguments |
|---------|-------------|-----------|
| `/play`  | Play a song or add it to the queue | `query` (YouTube URL or search keywords) |
| `/pause` | Pause the current playback | *None* |
| `/resume`| Resume the paused playback | *None* |
| `/skip`  | Skip the current playing song | *None* |
| `/queue` | Display the current server queue | *None* |
| `/loop`  | Toggle looping for the current song | *None* |
| `/stop`  | Stop playback and clear the queue | *None* |
| `/leave` | Disconnect from voice channel and clear queue | *None* |

---

## Configuration

Before running, create a `.env` file in the project root (you can copy `.env.example` as a starting point) and add your credentials:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token_here
```

### Discord Developer Portal Setup
Make sure the following settings are enabled on the [Discord Developer Portal](https://discord.com/developers/applications):
1. **Intents**: Go to **Bot** -> **Privileged Gateway Intents** and enable:
   - **Presence Intent**
   - **Server Members Intent**
   - **Message Content Intent**
2. **Scopes**: Invite the bot using the OAuth2 URL Generator with:
   - `bot` (with permissions `Connect`, `Speak`, `Send Messages`, `Embed Links`)
   - `applications.commands` (for Slash Commands support)

---

## Running with Docker (Recommended)

Using Docker is the easiest way to host the bot, as it packages Python, dependencies, and **FFmpeg** automatically.

### 1. Build the Docker Image
Navigate to the project root and run:
```bash
docker build -t secretary-kim-bot .
```

### 2. Run the Container
Run the bot in detached mode (background) while feeding the environment variables from your `.env` file:
```bash
docker run -d \
  --name secretary-kim \
  --env-file .env \
  --restart unless-stopped \
  secretary-kim-bot
```

### 3. Check Logs
To monitor the bot's logs:
```bash
docker logs -f secretary-kim
```

### 4. Stop the Bot
To stop and remove the container:
```bash
docker stop secretary-kim
docker rm secretary-kim
```

---

## Running Locally

If you prefer to run the bot locally without Docker, follow these steps:

### Prerequisites
1. **Python**: Ensure you have Python 3.13 or newer installed.
2. **uv**: We use `uv` for lightning-fast package management. Install it via `curl -LsSf https://astral.sh/uv/install.sh | sh`.
3. **FFmpeg**: You must have `ffmpeg` installed on your host system:
   - **Ubuntu/Debian**: `sudo apt update && sudo apt install ffmpeg`
   - **macOS** (via Homebrew): `brew install ffmpeg`
   - **Windows** (via Scoop/Choco): `scoop install ffmpeg` or `choco install ffmpeg`

### Setup & Launch
1. Synchronize python dependencies:
   ```bash
   uv sync
   ```
2. Start the bot:
   ```bash
   uv run python main.py
   ```
