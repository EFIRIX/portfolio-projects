# Windows autostart

Fast path: run `install_windows_task.bat`.

Manual setup:

1. Open Task Scheduler.
2. Create Task.
3. Trigger: At log on.
4. Action: Start a program.
5. Program: `C:\path\to\telegram-automation-bot\run.bat`
6. Start in: `C:\path\to\telegram-automation-bot`
7. Enable "Run whether user is logged on or not" only if you understand the credential storage tradeoff.

For `.ld`, install ffmpeg and make sure `ffmpeg.exe` is in `PATH`.

For no-VPN operation, set `TELEGRAM_PROXY_URLS` or `BOT_API_BASE_URLS` in `.env`. Check the active route with `/network_status`.
