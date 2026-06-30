from __future__ import annotations

import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app.config import load_settings, runtime_project_root
from app.config_import import ConfigImportError, load_import_config, merge_import_config
from app.secure_setup import DEFAULTS, generate_password, load_existing_for_setup
from services.secure_config import default_secure_config_path, delete_secure_config, masked_secure_config, save_secure_config


BG = "#0b1120"
PANEL = "#111827"
PANEL_2 = "#1f2937"
FIELD = "#020617"
TEXT = "#e5e7eb"
MUTED = "#94a3b8"
ACCENT = "#38bdf8"
DANGER = "#ef4444"
OK = "#22c55e"

EDITABLE_FIELDS = [
    ("BOT_TOKEN", "Bot token", True),
    ("OWNER_IDS", "Owner IDs", False),
    ("ADMIN_PASSWORD", "Web password", True),
    ("ARCHIVE_GROUP_ID", "Archive group ID", False),
    ("ARCHIVE_CHANNEL_ID", "Archive channel fallback", False),
    ("SOCKS_SEED_PROXIES", "Seed proxies", False),
    ("SOCKS_FEED_URLS", "Proxy feed URLs", False),
]


class TelegramAutomationGui:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Telegram Automation Bot")
        self.root.geometry("820x680")
        self.root.minsize(760, 620)
        self.root.configure(bg=BG)

        self.process: subprocess.Popen | None = None
        self.log_handle = None
        self.config_values: dict[str, str] = {}
        self.fields: dict[str, tk.Entry] = {}
        self.status_var = tk.StringVar(value="Ready")
        self.config_state_var = tk.StringVar(value="Config: checking...")
        self.bot_state_var = tk.StringVar(value="Bot: stopped")
        self.last_error_var = tk.StringVar(value="Last error: none")

        self._build_style()
        self._build_ui()
        self._load_existing()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(800, self._auto_start_if_ready)
        self.root.after(1200, self._poll_process)

    def run(self) -> None:
        self.root.mainloop()

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL_2, foreground=TEXT, padding=(16, 8), font=("Segoe UI", 10))
        style.map("TNotebook.Tab", background=[("selected", ACCENT)], foreground=[("selected", "#020617")])
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 20, "bold"))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=22)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="Telegram Automation Bot", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Import config, save it with Windows DPAPI, and run the bot from one launcher.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 14))

        self._build_status_strip(outer)

        notebook = ttk.Notebook(outer)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(14, 0))

        setup_tab = tk.Frame(notebook, bg=BG)
        runtime_tab = tk.Frame(notebook, bg=BG)
        logs_tab = tk.Frame(notebook, bg=BG)
        notebook.add(setup_tab, text="Setup")
        notebook.add(runtime_tab, text="Runtime")
        notebook.add(logs_tab, text="Logs")

        self._build_setup_tab(setup_tab)
        self._build_runtime_tab(runtime_tab)
        self._build_logs_tab(logs_tab)

    def _build_status_strip(self, parent: ttk.Frame) -> None:
        strip = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground="#243244")
        strip.pack(fill=tk.X)
        for text_var in (self.status_var, self.config_state_var, self.bot_state_var):
            tk.Label(strip, textvariable=text_var, bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(
                side=tk.LEFT, padx=12, pady=10
            )
        tk.Label(strip, text=f"Config: {default_secure_config_path()}", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(
            side=tk.RIGHT, padx=12, pady=10
        )

    def _build_setup_tab(self, parent: tk.Frame) -> None:
        form = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground="#243244")
        form.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        form.columnconfigure(1, weight=1)

        for row_index, (key, label, secret) in enumerate(EDITABLE_FIELDS):
            tk.Label(form, text=label, bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold")).grid(
                row=row_index, column=0, sticky="w", padx=16, pady=8
            )
            entry = tk.Entry(
                form,
                show="*" if secret else "",
                bg=FIELD,
                fg=TEXT,
                insertbackground=TEXT,
                relief=tk.FLAT,
                font=("Segoe UI", 10),
            )
            entry.grid(row=row_index, column=1, sticky="ew", padx=16, pady=8, ipady=7)
            self.fields[key] = entry

        hint = tk.Label(
            form,
            text="Import a config file or fill fields manually. Saved secrets are encrypted with Windows DPAPI.",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        hint.grid(row=len(EDITABLE_FIELDS), column=0, columnspan=2, sticky="w", padx=16, pady=(6, 12))

        buttons = tk.Frame(parent, bg=BG)
        buttons.pack(fill=tk.X, pady=(14, 0))
        self._button(buttons, "Import config", self._import_config, primary=True).pack(side=tk.LEFT, padx=(0, 10))
        self._button(buttons, "Save encrypted config", self._save_config, primary=True).pack(side=tk.LEFT, padx=(0, 10))
        self._button(buttons, "Show config", self._show_config).pack(side=tk.LEFT, padx=(0, 10))
        self._button(buttons, "Reset config", self._reset_config, danger=True).pack(side=tk.LEFT, padx=(0, 10))

    def _build_runtime_tab(self, parent: tk.Frame) -> None:
        card = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground="#243244")
        card.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        tk.Label(card, textvariable=self.bot_state_var, bg=PANEL, fg=TEXT, font=("Segoe UI", 15, "bold")).pack(
            anchor="w", padx=18, pady=(18, 4)
        )
        tk.Label(card, textvariable=self.last_error_var, bg=PANEL, fg=MUTED, font=("Segoe UI", 10)).pack(
            anchor="w", padx=18, pady=(0, 18)
        )
        tk.Label(card, text=f"Run log: {self._log_path()}", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(
            anchor="w", padx=18, pady=(0, 18)
        )

        buttons = tk.Frame(card, bg=PANEL)
        buttons.pack(anchor="w", padx=18, pady=(0, 18))
        self._button(buttons, "Start bot", self._start_bot, primary=True).pack(side=tk.LEFT, padx=(0, 10))
        self._button(buttons, "Stop bot", self._stop_bot).pack(side=tk.LEFT, padx=(0, 10))
        self._button(buttons, "Open web admin", self._open_web_admin).pack(side=tk.LEFT, padx=(0, 10))
        self._button(buttons, "Open logs", self._open_logs).pack(side=tk.LEFT, padx=(0, 10))

    def _build_logs_tab(self, parent: tk.Frame) -> None:
        panel = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground="#243244")
        panel.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        self.log_text = tk.Text(
            panel,
            bg=FIELD,
            fg=TEXT,
            insertbackground=TEXT,
            relief=tk.FLAT,
            wrap=tk.WORD,
            font=("Consolas", 9),
            height=18,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)
        buttons = tk.Frame(panel, bg=PANEL)
        buttons.pack(fill=tk.X, padx=14, pady=(0, 14))
        self._button(buttons, "Refresh logs", self._refresh_logs).pack(side=tk.LEFT, padx=(0, 10))
        self._button(buttons, "Open logs", self._open_logs).pack(side=tk.LEFT, padx=(0, 10))

    def _button(self, parent: tk.Frame, text: str, command, primary: bool = False, danger: bool = False) -> tk.Button:
        bg = ACCENT if primary else DANGER if danger else PANEL_2
        fg = "#020617" if primary else TEXT
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground="#7dd3fc" if primary else "#334155",
            activeforeground="#020617" if primary else TEXT,
            relief=tk.FLAT,
            padx=14,
            pady=9,
            font=("Segoe UI", 10, "bold" if primary else "normal"),
        )

    def _load_existing(self) -> None:
        self.config_values = merge_import_config({}, load_existing_for_setup())
        self._fill_fields(self.config_values, keep_secret_blanks=True)
        self._update_config_state()

    def _fill_fields(self, values: dict[str, str], keep_secret_blanks: bool = False) -> None:
        for key, entry in self.fields.items():
            entry.delete(0, tk.END)
            if keep_secret_blanks and key in {"BOT_TOKEN", "ADMIN_PASSWORD"} and values.get(key):
                continue
            if values.get(key):
                entry.insert(0, values[key])

    def _collect_values(self) -> dict[str, str]:
        values = dict(DEFAULTS)
        values.update({key: value for key, value in self.config_values.items() if str(value).strip()})
        for key, entry in self.fields.items():
            raw = entry.get().strip()
            if raw:
                values[key] = raw
        if not values.get("ADMIN_PASSWORD"):
            values["ADMIN_PASSWORD"] = generate_password()
        return values

    def _import_config(self) -> None:
        path = filedialog.askopenfilename(
            title="Import TelegramAutomationBot config",
            filetypes=[
                ("Config files", "*.json *.env *.txt"),
                ("JSON", "*.json"),
                ("ENV", "*.env"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            imported = load_import_config(Path(path))
        except ConfigImportError as exc:
            messagebox.showerror("Import failed", str(exc))
            return
        self.config_values = merge_import_config(self.config_values, imported)
        self._fill_fields(self.config_values)
        self.status_var.set("Imported config. Press Save encrypted config.")
        self._update_config_state()

    def _save_config(self) -> None:
        values = self._collect_values()
        if not values.get("BOT_TOKEN"):
            messagebox.showerror("Missing token", "BOT_TOKEN is required.")
            return
        if not values.get("OWNER_IDS"):
            messagebox.showerror("Missing owner", "OWNER_IDS is required.")
            return

        save_secure_config(values)
        self.config_values = values
        self._update_config_state()
        self.status_var.set("Config saved.")
        messagebox.showinfo("Saved", "Config saved with Windows DPAPI. You can start the bot now.")

    def _start_bot(self) -> None:
        if self.process and self.process.poll() is None:
            self.bot_state_var.set("Bot: running")
            return
        try:
            settings = load_settings()
        except Exception as exc:
            messagebox.showerror("Config error", str(exc))
            return
        if not settings.bot_token or not settings.owner_ids:
            messagebox.showerror("Missing config", "Import or save BOT_TOKEN and OWNER_IDS first.")
            return

        try:
            log_path = self._log_path()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_handle = log_path.open("a", encoding="utf-8", buffering=1)
            self.log_handle.write("\n=== GUI start ===\n")
            self.process = subprocess.Popen(
                self._bot_command(),
                cwd=str(runtime_project_root()),
                stdout=self.log_handle,
                stderr=subprocess.STDOUT,
            )
        except Exception as exc:
            self._close_log_handle()
            self.status_var.set(f"Start failed: {exc}")
            messagebox.showerror("Start failed", str(exc))
            return
        self.bot_state_var.set("Bot: running")
        self.status_var.set("Bot running. Telegram control is active.")

    def _stop_bot(self) -> None:
        if not self.process or self.process.poll() is not None:
            self.bot_state_var.set("Bot: stopped")
            return
        self.process.terminate()
        self.bot_state_var.set("Bot: stopping...")
        threading.Thread(target=self._wait_stop, daemon=True).start()

    def _wait_stop(self) -> None:
        if not self.process:
            return
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self._close_log_handle()
        self.root.after(0, lambda: self.bot_state_var.set("Bot: stopped"))

    def _open_web_admin(self) -> None:
        try:
            settings = load_settings()
            url = f"http://{settings.web_host}:{settings.web_port}/"
        except Exception:
            url = "http://127.0.0.1:8000/"
        webbrowser.open(url)

    def _open_logs(self) -> None:
        log_path = self._log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.touch(exist_ok=True)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(log_path)])
        else:
            webbrowser.open(log_path.as_uri())

    def _show_config(self) -> None:
        config = masked_secure_config()
        if not config:
            messagebox.showinfo("Config", "No secure config saved yet.")
            return
        lines = [f"{key}={config[key]}" for key in sorted(config)]
        messagebox.showinfo("Config", "\n".join(lines))

    def _reset_config(self) -> None:
        if not messagebox.askyesno("Reset config", "Delete saved secure config?"):
            return
        delete_secure_config()
        self.config_values = dict(DEFAULTS)
        self._fill_fields(self.config_values)
        self.status_var.set("Config deleted.")
        self._update_config_state()

    def _auto_start_if_ready(self) -> None:
        try:
            settings = load_settings()
        except Exception:
            return
        if settings.bot_token and settings.owner_ids:
            self._start_bot()

    def _poll_process(self) -> None:
        if self.process and self.process.poll() is not None:
            code = self.process.returncode
            self.process = None
            self._close_log_handle()
            if code == 0:
                self.bot_state_var.set("Bot: stopped")
                self.last_error_var.set("Last error: none")
            else:
                tail = self._read_log_tail(12)
                self.bot_state_var.set(f"Bot: crashed ({code})")
                self.last_error_var.set(f"Last error: see {self._log_path()}")
                self.status_var.set(f"Bot exited with code {code}.")
                self._set_log_text(tail)
        self.root.after(1200, self._poll_process)

    def _refresh_logs(self) -> None:
        self._set_log_text(self._read_log_tail(120))

    def _set_log_text(self, text: str) -> None:
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, text or "No logs yet.")
        self.log_text.see(tk.END)

    def _read_log_tail(self, lines: int) -> str:
        path = self._log_path()
        if not path.exists():
            return ""
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])

    def _update_config_state(self) -> None:
        try:
            settings = load_settings()
            ok = bool(settings.bot_token and settings.owner_ids)
        except Exception:
            ok = bool(self.config_values.get("BOT_TOKEN") and self.config_values.get("OWNER_IDS"))
        self.config_state_var.set("Config: OK" if ok else "Config: missing")

    def _bot_command(self) -> list[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable, "--run-bot"]
        return [sys.executable, "-m", "app", "--run-bot"]

    def _log_path(self) -> Path:
        return runtime_project_root() / "logs" / "gui-bot-run.log"

    def _close_log_handle(self) -> None:
        if self.log_handle:
            self.log_handle.close()
            self.log_handle = None

    def _on_close(self) -> None:
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("Exit", "Stop the bot and close launcher?"):
                return
            self.process.terminate()
            time.sleep(0.3)
        self._close_log_handle()
        self.root.destroy()


def run_gui() -> None:
    TelegramAutomationGui().run()
