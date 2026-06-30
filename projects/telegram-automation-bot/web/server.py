from __future__ import annotations

import html
import secrets
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.config import Settings
from services.platform_checks import PlatformReport
from storage.database import Database


SESSION_COOKIE = "tab_session"


def create_web_app(settings: Settings, db: Database, report: PlatformReport) -> FastAPI:
    app = FastAPI(title="Telegram Automation Bot Admin")
    app.state.sessions = set()

    def is_authenticated(request: Request) -> bool:
        token = request.cookies.get(SESSION_COOKIE)
        return bool(token and token in app.state.sessions)

    def require_admin(request: Request) -> None:
        if not is_authenticated(request):
            raise HTTPException(status_code=303, headers={"Location": "/login"})

    @app.middleware("http")
    async def auth_redirect_middleware(request: Request, call_next: Any) -> Any:
        public_paths = {"/login", "/favicon.ico"}
        if request.url.path not in public_paths and not is_authenticated(request):
            return RedirectResponse("/login", status_code=303)
        return await call_next(request)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> str:
        error = request.query_params.get("error") == "1"
        return login_html(error)

    @app.post("/login")
    async def login(request: Request) -> RedirectResponse:
        body = (await request.body()).decode("utf-8", errors="ignore")
        values = parse_qs(body)
        password = values.get("password", [""])[0]
        if not secrets.compare_digest(password, settings.admin_password):
            return RedirectResponse("/login?error=1", status_code=303)
        token = secrets.token_urlsafe(32)
        app.state.sessions.add(token)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=60 * 60 * 12,
        )
        return response

    @app.get("/logout")
    async def logout(request: Request) -> RedirectResponse:
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            app.state.sessions.discard(token)
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        return response

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> str:
        require_admin(request)
        checks = "".join(row(item.name, item.detail, "ok" if item.ok else "warn") for item in report.items)
        business = db.business_summary()
        return page(
            "Dashboard",
            f"""
            <section class="hero">
              <div>
                <p class="eyebrow">REMOTE CONTROL</p>
                <h2>Chat Automation is online</h2>
                <p class="muted">Local web admin for the home machine. Remote control stays in Telegram.</p>
              </div>
              <span class="status-pill">Polling active</span>
            </section>
            <div class="grid">
              {card("Messages", str(db.count("messages")), "Cached incoming updates")}
              {card("Events", str(db.count("events")), "Runtime and bot actions")}
              {card("Media", str(db.count("media")), "Saved files")}
              {card("Business", "Connected" if business["enabled"] else "Not connected", "can_reply: " + ("yes" if business["can_reply"] else "no"))}
            </div>
            <h2>Runtime checks</h2>
            <table>{checks}</table>
            """,
        )

    @app.get("/events", response_class=HTMLResponse)
    async def events(request: Request) -> str:
        require_admin(request)
        rows = "".join(row(e["created_at"], f"{e['level']} {e['event_type']} {html.escape(str(e.get('payload', '')))}") for e in db.last_events(100))
        return page("Events", f"<table>{rows}</table>")

    @app.get("/chats", response_class=HTMLResponse)
    async def chats(request: Request) -> str:
        require_admin(request)
        rows = "".join(row(str(c["chat_id"]), f"{c['messages']} messages, last seen {c['last_seen']}") for c in db.known_chats(100))
        return page("Chats", f"<table>{rows}</table>")

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request) -> str:
        require_admin(request)
        rows = "".join(
            row(f"{s['scope']} / {s['key']}", f"chat={s['chat_id']} user={s['user_id']} value={html.escape(s['value'])}")
            for s in db.settings(200)
        )
        return page("Settings", f"<table>{rows}</table>")

    @app.get("/media", response_class=HTMLResponse)
    async def media(request: Request) -> str:
        require_admin(request)
        rows = "".join(row(m["created_at"], f"{m['media_type']} {html.escape(m['path'])}") for m in db.last_media(100))
        return page("Media", f"<table>{rows}</table>")

    @app.get("/features", response_class=HTMLResponse)
    async def features(request: Request) -> str:
        require_admin(request)
        body = """
        <table>
          <tr><td>Message edits</td><td class="ok">active where Telegram sends edited_message</td></tr>
          <tr><td>Message deletes</td><td class="warn">limited to official Business deletion updates</td></tr>
          <tr><td>Timed media</td><td class="warn">limited to files Telegram delivers to the bot</td></tr>
          <tr><td>Chat recovery</td><td class="warn">metadata/cache only; Telegram does not let bots restore private chats</td></tr>
          <tr><td>Owner commands</td><td class="ok">active</td></tr>
        </table>
        """
        return page("Feature status", body)

    @app.get("/business", response_class=HTMLResponse)
    async def business(request: Request) -> str:
        require_admin(request)
        summary = db.business_summary()
        rows = "".join(
            row(str(item["connection_id"]), f"user={item['user_id']} enabled={item['is_enabled']} can_reply={item['can_reply']} updated={item['updated_at']}")
            for item in db.last_business_connections(50)
        )
        setup = (
            "<div class='panel'><h3>Business setup</h3>"
            "<p>Open @BotFather -> Bot Settings -> Business Mode -> Enable. "
            "Then Telegram Settings -> Telegram Business -> Chatbots -> add @aerixseebot.</p></div>"
        )
        return page(
            "Business",
            f"{card('State', 'Connected' if summary['enabled'] else 'Not connected', 'can_reply: ' + ('yes' if summary['can_reply'] else 'no'))}{setup}<table>{rows}</table>",
        )

    @app.get("/api/status")
    async def api_status(request: Request) -> JSONResponse:
        require_admin(request)
        return JSONResponse(
            {
                "messages": db.count("messages"),
                "events": db.count("events"),
                "media": db.count("media"),
                "business": db.business_summary(),
                "checks": [item.as_dict() for item in report.items],
            }
        )

    @app.post("/api/settings/{scope}/{key}")
    async def api_setting(scope: str, key: str, request: Request) -> JSONResponse:
        require_admin(request)
        body: dict[str, Any] = await request.json()
        db.set_setting(scope, key, str(body.get("value", "")), body.get("chat_id"), body.get("user_id"))
        return JSONResponse({"ok": True})

    return app


def login_html(error: bool = False) -> str:
    message = "<p class='error'>Wrong password</p>" if error else ""
    return f"""
    <!doctype html>
    <html lang="en">
    <head>{head("Login")}</head>
    <body class="login-body">
      <main class="login-shell">
        <form class="login-card" method="post" action="/login">
          <div class="mark">CA</div>
          <p class="eyebrow">PRIVATE DASHBOARD</p>
          <h1>Chat Automation</h1>
          <p class="muted">Enter the local admin password from <code>.env</code>.</p>
          {message}
          <label>Password</label>
          <input name="password" type="password" autocomplete="current-password" autofocus>
          <button type="submit">Open dashboard</button>
        </form>
      </main>
    </body>
    </html>
    """


def page(title: str, body: str) -> str:
    nav = (
        "<nav>"
        "<a href='/'>Dashboard</a><a href='/events'>Events</a><a href='/chats'>Chats</a>"
        "<a href='/settings'>Settings</a><a href='/media'>Media</a><a href='/business'>Business</a>"
        "<a href='/features'>Features</a><a href='/logout'>Logout</a>"
        "</nav>"
    )
    return f"""
    <!doctype html>
    <html lang="en">
    <head>{head(title)}</head>
    <body>
      <header><div><p class="eyebrow">LOCAL ADMIN</p><h1>Telegram Automation Bot</h1></div></header>
      {nav}
      <main><h2>{html.escape(title)}</h2>{body}</main>
    </body>
    </html>
    """


def head(title: str) -> str:
    return f"""
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{html.escape(title)}</title>
      <style>
        :root {{ color-scheme: dark; --bg:#0a0f1c; --panel:#111827; --panel2:#172033; --line:#243047; --text:#eef5ff; --muted:#93a4bb; --blue:#1d9bf0; --green:#36d399; --amber:#fbbf24; }}
        * {{ box-sizing:border-box; }}
        body {{ margin:0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; background:radial-gradient(circle at top left, #123252 0, var(--bg) 34rem); color:var(--text); }}
        header {{ padding:26px 32px; border-bottom:1px solid rgba(255,255,255,.08); background:rgba(10,15,28,.72); backdrop-filter:blur(18px); }}
        h1,h2,h3,p {{ margin-top:0; }}
        h1 {{ margin-bottom:0; font-size:26px; }}
        h2 {{ font-size:25px; }}
        nav {{ display:flex; gap:8px; padding:12px 28px; background:rgba(17,24,39,.82); border-bottom:1px solid rgba(255,255,255,.08); flex-wrap:wrap; position:sticky; top:0; backdrop-filter:blur(16px); }}
        nav a {{ color:#d8ebff; text-decoration:none; font-weight:700; padding:9px 12px; border:1px solid transparent; border-radius:8px; }}
        nav a:hover {{ border-color:rgba(29,155,240,.55); background:rgba(29,155,240,.12); }}
        main {{ max-width:1120px; margin:0 auto; padding:30px; }}
        table {{ width:100%; border-collapse:collapse; background:rgba(17,24,39,.88); border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
        td {{ padding:13px 14px; border-bottom:1px solid rgba(255,255,255,.06); vertical-align:top; color:#dbe7f5; }}
        .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap:14px; margin-bottom:28px; }}
        .card,.panel {{ background:linear-gradient(180deg, rgba(23,32,51,.96), rgba(17,24,39,.96)); border:1px solid var(--line); border-radius:8px; padding:18px; box-shadow:0 18px 40px rgba(0,0,0,.22); }}
        .label {{ color:var(--muted); font-size:13px; text-transform:uppercase; letter-spacing:.08em; }}
        .value {{ font-size:27px; font-weight:800; margin-top:8px; overflow-wrap:anywhere; }}
        .desc,.muted {{ color:var(--muted); }}
        .ok {{ color:var(--green); }}
        .warn {{ color:var(--amber); }}
        .eyebrow {{ color:#7dd3fc; font-size:12px; font-weight:800; text-transform:uppercase; letter-spacing:.12em; margin-bottom:8px; }}
        .hero {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-start; padding:22px; background:linear-gradient(135deg, rgba(29,155,240,.18), rgba(54,211,153,.10)); border:1px solid rgba(125,211,252,.26); border-radius:8px; margin-bottom:16px; }}
        .status-pill {{ padding:8px 10px; border:1px solid rgba(54,211,153,.45); border-radius:999px; color:#b8ffe4; white-space:nowrap; }}
        .login-body {{ min-height:100vh; display:grid; place-items:center; padding:22px; }}
        .login-shell {{ width:min(430px, 100%); padding:0; }}
        .login-card {{ background:rgba(17,24,39,.92); border:1px solid var(--line); border-radius:8px; padding:28px; box-shadow:0 26px 70px rgba(0,0,0,.38); }}
        .mark {{ width:48px; height:48px; border-radius:8px; display:grid; place-items:center; background:linear-gradient(135deg, var(--blue), #36d399); font-weight:900; margin-bottom:18px; }}
        label {{ display:block; color:#c8d6e8; margin:18px 0 8px; font-weight:700; }}
        input {{ width:100%; padding:13px 12px; border-radius:8px; border:1px solid var(--line); background:#0b1220; color:var(--text); font-size:16px; }}
        button {{ width:100%; margin-top:16px; padding:13px 14px; border:0; border-radius:8px; background:var(--blue); color:white; font-size:16px; font-weight:800; cursor:pointer; }}
        code {{ color:#bfdbfe; }}
        .error {{ color:#fecaca; background:rgba(239,68,68,.12); border:1px solid rgba(239,68,68,.35); padding:10px; border-radius:8px; }}
      </style>
    """


def card(label: str, value: str, description: str = "") -> str:
    return (
        "<div class='card'>"
        f"<div class='label'>{html.escape(label)}</div>"
        f"<div class='value'>{html.escape(value)}</div>"
        f"<div class='desc'>{html.escape(description)}</div>"
        "</div>"
    )


def row(left: str, right: str, cls: str = "") -> str:
    class_attr = f" class='{cls}'" if cls else ""
    return f"<tr><td>{html.escape(left)}</td><td{class_attr}>{html.escape(right)}</td></tr>"
