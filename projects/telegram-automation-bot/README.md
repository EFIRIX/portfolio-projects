# Telegram Automation Bot

Local Telegram automation bot with remote owner controls and a local web admin panel.

## What works in v1

- Remote owner commands in Telegram: `/status`, `/logs`, `/chats`, `/settings`, `/media`, `/help_admin`, `/enable_feature`, `/disable_feature`.
- Chat commands for owners only: `.spam`, `.mute`, `.unmute`, `.sw`, `.ld`, `.ynd`, `.chp`, `.ai`, `.ang`, `.unang`, `.kind`, `.unkind`, `.bw`, `.wbl`, `.unbw`, `.unwbl`.
- Message edit tracking for updates Telegram sends to the bot.
- Business deletion tracking for official `deleted_business_messages` updates.
- Local storage in SQLite and `media/`.
- Local web admin at `WEB_HOST:WEB_PORT`.
- macOS and Windows launch/build helpers.

## Important Telegram limitation

Telegram Bot API does not give a normal bot hidden access to all personal chats, deleted ordinary messages, or self-destructing media. This project only processes events and files Telegram officially delivers to the bot or a connected Telegram Business bot.

## Quick start

```bash
cd telegram-automation-bot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
cp .env.example .env
python -m app
```

On Windows:

```bat
cd telegram-automation-bot
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
python -m pip install -r requirements.txt
copy .env.example .env
run.bat
```

Edit `.env` before starting:

- `BOT_TOKEN`: token from BotFather.
- `OWNER_IDS`: comma-separated Telegram user IDs allowed to control the bot.
- `ADMIN_PASSWORD`: password for the local web admin.

## Telegram usage

Run the bot at home and control it from Telegram:

- `/start` or `/menu` opens the inline control menu.
- `/status` shows runtime status.
- `/network_status` shows the active Telegram API route.
- `/network_test` checks direct, custom API, and proxy routes.
- `/proxy_status` shows SOCKS/HTTP proxy feed state.
- `/proxy_refresh` refreshes and checks SOCKS/HTTP proxy candidates.
- `/mtproxy_status` shows MTProto proxy fallback state.
- `/mtproxy_refresh` refreshes MTProxy candidates from configured feeds.
- `/logs` sends recent events.
- `/settings` lists enabled modes.
- `/media` lists recent saved files.
- `/business_setup` shows Telegram Business connection steps.
- `/archive_setup` shows archive channel setup.
- `/archive_status` shows cloned message count.
- `/clone_existing_chats [limit]` creates missing forum topics for chats already known in the local index and archives available cached media/cards.
- `/help_admin` shows commands.

## Chat archive forum

The bot can clone every message it receives into a private Telegram forum group. Each dialog gets one topic named like `@peer - @owner`, so the peer's messages and your replies stay in the same thread. The local SQLite database stores only technical mappings from source messages to archive posts.

Recommended setup:

1. Create a private Telegram group.
2. Convert it to a supergroup if Telegram asks.
3. Enable Topics/Forum.
4. Add the bot as admin.
5. Give it permission to send messages and manage topics.
6. Send `/set_archive_group` inside that group, or forward any message from the group to the bot.

Set the group in `.env`:

```env
ARCHIVE_MODE=forum
ARCHIVE_GROUP_ID=-100...
```

The old channel mirror can stay as fallback:

```env
ARCHIVE_CHANNEL_ID=-1004397482368
```

One-see/self-destructing media is archived only if Telegram Business API actually sends a usable `file_id` to the bot.

To create topics for chats the bot already saw, run:

```text
/clone_existing_chats
```

This can only clone what is already in the local SQLite index. Telegram Bot API does not provide old chat history retroactively, so messages the bot never received cannot be fetched by this command.

## Windows and no-VPN networking

The bot can run on Windows without a manual VPN if you provide at least one reachable Telegram API route. It tries routes in this order: direct Telegram API, custom Bot API gateway, Telegram API through proxy, custom gateway through proxy.

```env
NETWORK_MODE=auto
BOT_API_BASE_URLS=https://api.telegram.org
TELEGRAM_PROXY_URLS=socks5://user:pass@host:port,http://host:port
TELEGRAM_CONNECT_TIMEOUT=10
TELEGRAM_RETRY_MIN_SECONDS=5
TELEGRAM_RETRY_MAX_SECONDS=120
SOCKS_FEED_ENABLED=1
SOCKS_FEED_REFRESH_SECONDS=900
SOCKS_FEED_URLS=
SOCKS_SEED_PROXIES=socks5://user:pass@host:port,http://host:port
SOCKS_MAX_CANDIDATES=100
```

Do not use random public proxies for a real bot token. Use a proxy or HTTPS gateway you control/trust. If every route is blocked, the web-admin remains online and the bot keeps retrying with backoff.

Without `my.telegram.org`, the recommended no-VPN fallback is SOCKS/HTTP proxy feeds. Put at least one trusted proxy in `SOCKS_SEED_PROXIES`, or add raw proxy-list URLs to `SOCKS_FEED_URLS`. The bot checks candidates with `getMe` and automatically uses a working route.

Windows helpers:

- `run.bat` creates `.venv`, installs requirements, and writes `logs/windows-run.log`.
- `install_windows_task.bat` installs an autostart task.
- `restart_windows.bat` restarts the scheduled task if installed.

## Standalone Windows EXE

For the clean Windows mode, build a single GUI `TelegramAutomationBot.exe`. It does not need Python, `.venv`, `.env`, `requirements.txt`, or `.bat` files next to it when you run it.

Build on Windows:

```bat
build_windows_exe.bat
```

The build script also supports the Parallels shared folder path:

```text
C:\Mac\Home\Documents\untitled folder 2\telegram-automation-bot
```

It writes build logs to `logs\build-windows-exe.log`.

Output:

```text
dist\TelegramAutomationBot.exe
```

First run: double-click `dist\TelegramAutomationBot.exe`. The GUI launcher opens setup/runtime/log tabs and has:

- `Import config`
- `Save encrypted config`
- `Start bot`
- `Stop`
- `Open web admin`
- `Open logs`
- `Show config`
- `Reset`

The build script copies `TelegramAutomationBot-import.json` next to the exe. Use it like this:

1. Click `Import config`.
2. Select `TelegramAutomationBot-import.json`.
3. Click `Save encrypted config`.
4. Click `Start bot`.

The setup asks for:

- `BOT_TOKEN`
- `OWNER_IDS`
- `ADMIN_PASSWORD`
- `ARCHIVE_GROUP_ID`
- optional archive channel and proxy settings

Secrets are not embedded into the exe. They are stored in `%APPDATA%\TelegramAutomationBot\config.json` encrypted with Windows DPAPI for the current Windows user. Runtime files are also created under `%APPDATA%\TelegramAutomationBot\`, including SQLite, media, and logs.

GUI bot-start logs are written here:

```text
%APPDATA%\TelegramAutomationBot\logs\gui-bot-run.log
```

Useful maintenance commands are available from a terminal in dev/console builds, but the GUI is the main mode for the onefile exe:

```bat
TelegramAutomationBot.exe --show-config
TelegramAutomationBot.exe --reset-config
```

`--show-config` masks secrets and proxy passwords. `--reset-config` deletes the saved DPAPI config.

Autostart for the exe:

```bat
install_windows_task_exe.bat
```

Security note: an exe that starts without any password cannot make embedded secrets impossible to extract. This build avoids embedding secrets at all; DPAPI protects them in the Windows user profile instead.

## MTProto proxy notes

MTProto proxies from Telegram channels such as `@ProxyMTProto` are not HTTPS/SOCKS proxies, so they cannot be used by the normal Bot API session directly. Without `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` from `my.telegram.org`, MTProto fallback stays disabled.

Configure:

```env
MTPROXY_ENABLED=0
MTPROXY_REFRESH_SECONDS=900
MTPROXY_FEED_URLS=https://t.me/s/ProxyMTProto
MTPROXY_CHANNELS=ProxyMTProto
MTPROXY_SEED_PROXIES=
MTPROXY_MAX_CANDIDATES=50
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELETHON_BOT_SESSION=./data/telethon-bot.session
TELETHON_USER_SESSION=./data/telethon-user.session
TELETHON_USER_FEED_ENABLED=0
```

Get `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` from `https://my.telegram.org`. If the public `t.me/s/...` feed is blocked too, create a user session:

```bash
python -m app.telethon_login
```

Then set `TELETHON_USER_FEED_ENABLED=1`. In fallback mode only basic owner commands work: `/status`, `/network_status`, `/network_test`, `/logs`, `/help_admin`, `/mtproxy_status`, `/mtproxy_refresh`. Business/archive features return when Bot API is reachable again.

## Business Mode fix

If Telegram on iPhone shows `This bot doesn't support Telegram Business yet`, the bot code is not enough by itself. Telegram also requires Business Mode to be enabled for the bot in BotFather.

1. Open `@BotFather`.
2. Select your bot.
3. Open `Bot Settings`.
4. Open `Business Mode`.
5. Enable Business Mode.
6. In Telegram app open `Settings -> Telegram Business -> Chatbots`.
7. Add `@aerixseebot` and press `Add`.

After this, the bot can receive official Business updates such as `business_connection`, `business_message`, `edited_business_message`, and `deleted_business_messages`.

The Telegram menu shows whether a Business connection has reached the bot and whether `can_reply` is enabled.

## Web admin login

The project is Telegram-first. The local web dashboard is only a helper screen for the home machine.

Open `http://127.0.0.1:8000/`. It uses a local login form.

- Password: `ADMIN_PASSWORD` from `.env`.
- Current default from `.env.example`: `change-me`.

## ffmpeg

`.ld` needs `ffmpeg`.

- macOS: `brew install ffmpeg`
- Windows: put `ffmpeg.exe` in `PATH` or next to the app executable.

## Packaging

Use PyInstaller from the target OS:

```bash
python -m pip install pyinstaller
pyinstaller packaging/TelegramAutomationBot.spec
```

The `.env` file stays external and should be placed next to the executable or in the project directory.

For the clean Windows onefile build, use:

```bat
pyinstaller --clean packaging\TelegramAutomationBot-onefile.spec
```

This onefile target intentionally does not bundle `.env` or `.env.example`; use the GUI setup instead.
