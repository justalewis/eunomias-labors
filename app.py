#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Eunomia's Labors — a four-page site offering DOI registration and Crossref
reference backfilling to rhetoric and composition journals.

Server-rendered Flask, no JavaScript framework, deliberately small. The one
moving part is the coverage table, which reads data/coverage.json — refreshed
nightly by crossref_refresh.py — so the argument on the landing page updates
itself as journals deposit.
"""
from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import smtplib
import sqlite3
import time
from collections import OrderedDict, deque
from email.message import EmailMessage
from pathlib import Path
from threading import Lock

from flask import (Flask, abort, g, redirect, render_template, request,
                   send_from_directory, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix

BASE = Path(__file__).parent
# journals.json ships in the image; coverage.json and the SQLite file are
# written at runtime and must live on the mounted volume, or the nightly
# refresh writes a path the deployed app never reads.
DATA = Path(os.environ.get("EUNOMIA_DATA") or BASE / "data")
COVERAGE = DATA / "coverage.json"
DB_PATH = Path(os.environ.get("EUNOMIA_DB", DATA / "submissions.sqlite3"))

CONTACT_EMAIL = "jlewis2@olympic.edu"
# The copy routes the "something on my end broke" message to a different
# address than the confirmation screen.
FALLBACK_EMAIL = "justalewis1@gmail.com"
PINAKES_URL = "https://pinakes.xyz"
AUDITOR_URL = "https://github.com/justalewis/crossref-references-deposit-auditor"
GITHUB_URL = "https://github.com/justalewis"
REDACTION_URL = "https://pinakes.xyz/redaction-request"

# python:3.12-slim has no /etc/mime.types, so mimetypes guesses
# application/octet-stream for these. Combined with the nosniff header that
# makes some browsers refuse the fonts outright, so register them explicitly.
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("image/avif", ".avif")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/svg+xml", ".svg")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # a contact form needs nothing larger

# Fly terminates TLS at its proxy and forwards over plain HTTP, so without this
# request.base_url reports http:// and every canonical and og:url on the site
# points at the insecure scheme. One proxy hop, so x_for/x_proto/x_host = 1.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

CANONICAL_HOST = os.environ.get("CANONICAL_HOST", "")

# --------------------------------------------------------------------------
# Coverage data
# --------------------------------------------------------------------------

EMPTY_COVERAGE = {"generated": None, "journals": [], "totals": {}}

_coverage_cache: dict = {"mtime": None, "payload": None}
_coverage_lock = Lock()


def coverage() -> dict:
    """Read data/coverage.json, re-reading only when the file changes on disk.

    Returns an empty-but-valid shape if the file is missing or unreadable, so a
    fresh checkout renders rather than 500s. This runs on every request via the
    context processor, so a corrupt file must not be able to take the whole site
    down — including the 404 page, which renders the same base template.
    """
    try:
        mtime = COVERAGE.stat().st_mtime
    except OSError:
        return _coverage_cache["payload"] or EMPTY_COVERAGE

    with _coverage_lock:
        if _coverage_cache["mtime"] != mtime:
            try:
                _coverage_cache["payload"] = json.loads(COVERAGE.read_text(encoding="utf-8"))
                _coverage_cache["mtime"] = mtime
            except (OSError, ValueError):
                app.logger.exception("coverage.json is unreadable; serving last good copy.")
                return _coverage_cache["payload"] or EMPTY_COVERAGE
        return _coverage_cache["payload"]


# --------------------------------------------------------------------------
# Submissions
# --------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at   TEXT NOT NULL DEFAULT (datetime('now')),
    name          TEXT NOT NULL,
    email         TEXT NOT NULL,
    journal       TEXT NOT NULL,
    archive_url   TEXT NOT NULL,
    role          TEXT,
    standing      TEXT,
    hoping_for    TEXT,
    notes         TEXT,
    wants_call    INTEGER NOT NULL DEFAULT 0
);
"""


def db() -> sqlite3.Connection:
    if "db" not in g:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.executescript(SCHEMA)
    return g.db


@app.teardown_appcontext
def close_db(_exception) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def store(fields: dict) -> None:
    connection = db()
    connection.execute(
        "INSERT INTO submissions "
        "(name, email, journal, archive_url, role, standing, hoping_for, notes, wants_call) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (fields["name"], fields["email"], fields["journal"], fields["archive_url"],
         fields["role"], fields["standing"], fields["hoping_for"], fields["notes"],
         1 if fields["wants_call"] else 0),
    )
    connection.commit()


def notify(fields: dict) -> None:
    """Email the submission on. Silently skipped when SMTP isn't configured —
    the row is already in SQLite, so nothing is lost either way."""
    host = os.environ.get("SMTP_HOST")
    if not host:
        app.logger.info("SMTP_HOST unset; submission stored but not emailed.")
        return

    # Everything, including building the message, sits inside the try. A stray
    # control character in a header makes EmailMessage raise, and that must not
    # surface as a 500 after the row has already been committed.
    try:
        message = EmailMessage()
        message["Subject"] = f"Eunomia's Labors — {fields['journal']}"
        message["From"] = os.environ.get("SMTP_FROM", CONTACT_EMAIL)
        message["To"] = os.environ.get("NOTIFY_TO", CONTACT_EMAIL)
        message["Reply-To"] = fields["email"]
        message.set_content(
            f"{fields['name']} <{fields['email']}>\n"
            f"Journal:  {fields['journal']}\n"
            f"Archive:  {fields['archive_url']}\n"
            f"Role:     {fields['role'] or '-'}\n"
            f"Standing: {fields['standing'] or '-'}\n"
            f"Wants:    {fields['hoping_for'] or '-'}\n"
            f"Call?     {'yes' if fields['wants_call'] else 'no'}\n\n"
            f"{fields['notes'] or ''}\n"
        )
        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            user = os.environ.get("SMTP_USER")
            if user:
                server.login(user, os.environ.get("SMTP_PASSWORD", ""))
            server.send_message(message)
    except Exception:  # noqa: BLE001 — never lose a submission to a mail failure
        app.logger.exception("Could not email submission; it is stored in SQLite.")


def auto_reply(fields: dict) -> None:
    """Acknowledge the sender, so their first experience is a reply rather than
    silence. Swallows its own errors: the row is stored either way, and an
    acknowledgement is never worth a 500."""
    host = os.environ.get("SMTP_HOST")
    if not host:
        return

    try:
        message = EmailMessage()
        message["Subject"] = f"Your note about {fields['journal']}"
        message["From"] = os.environ.get("SMTP_FROM", CONTACT_EMAIL)
        message["To"] = fields["email"]
        message.set_content(
            "Thanks for writing. I'll have a real answer for you within a few days.\n"
            "\n"
            "Thank you so, so much for writing!\n"
            "\n"
            "— Justin\n"
        )
        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            user = os.environ.get("SMTP_USER")
            if user:
                server.login(user, os.environ.get("SMTP_PASSWORD", ""))
            server.send_message(message)
    except Exception:  # noqa: BLE001
        app.logger.exception("Could not send the auto-reply; the submission is stored.")


# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------

RATE_WINDOW = 3600       # one hour, per client

# Two ceilings, because they guard different things. ATTEMPTS covers every POST
# and stops a flood; ACCEPTED covers only submissions that validated and were
# stored, so an editor who mistypes their email four times isn't locked out for
# an hour by their own typos.
MAX_ATTEMPTS = 30
MAX_ACCEPTED = 5

# Ordered by recency so the hard ceiling can evict least-recently-seen first.
MAX_CLIENTS = 20000
_hits: "OrderedDict[str, dict[str, deque]]" = OrderedDict()
_hits_lock = Lock()
_last_sweep = 0.0


def rate_key(client: str) -> str:
    """One bucket per client. IPv6 collapses to its /64, because a routed /64 is
    the standard allocation for a VPS — keying on the full address would hand an
    attacker 2**64 free buckets and switch the limiter off entirely."""
    try:
        address = ipaddress.ip_address(client)
    except ValueError:
        return client
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return client


def _bucket(client: str, kind: str, now: float) -> deque:
    buckets = _hits.get(client)
    if buckets is None:
        buckets = _hits[client] = {"attempt": deque(), "accepted": deque()}
    _hits.move_to_end(client)
    seen = buckets[kind]
    while seen and now - seen[0] > RATE_WINDOW:
        seen.popleft()
    return seen


def rate_limited(client: str, kind: str) -> bool:
    """Record one event of `kind` and report whether the client is over its ceiling."""
    ceiling = MAX_ATTEMPTS if kind == "attempt" else MAX_ACCEPTED
    now = time.time()
    with _hits_lock:
        seen = _bucket(client, kind, now)
        if len(seen) >= ceiling:
            return True
        seen.append(now)

        # Keep the dict from growing without bound. The sweep is throttled
        # because under a flood every key carries a fresh timestamp, so an
        # unthrottled O(n) scan would run on every POST while holding the lock.
        global _last_sweep
        if now - _last_sweep > 60:
            _last_sweep = now
            stale = [key for key, buckets in _hits.items()
                     if all(not d or now - d[-1] > RATE_WINDOW for d in buckets.values())]
            for key in stale:
                _hits.pop(key, None)

        # Hard ceiling, least-recently-seen first. Losing a bucket only ever
        # grants a client a fresh allowance, never a lockout.
        while len(_hits) > MAX_CLIENTS:
            _hits.popitem(last=False)
        return False


def client_id() -> str:
    """The client's address. Fly's proxy sets Fly-Client-IP on everything it
    forwards, but the header is only trustworthy when we are actually behind
    that proxy — Fly injects FLY_APP_NAME into every Machine. Off Fly it is
    plain client input, and trusting it would let anyone pick their own rate
    bucket, or claim an editor's address and lock that person out."""
    if os.environ.get("FLY_APP_NAME"):
        forwarded = request.headers.get("Fly-Client-IP")
        if forwarded:
            return forwarded
    return request.remote_addr or "unknown"


# --------------------------------------------------------------------------
# Template globals and security headers
# --------------------------------------------------------------------------

@app.context_processor
def inject_globals() -> dict:
    return {
        "site_name": "Eunomia's Labors",
        "tagline": "DOIs and reference lists for Rhet/Comp journals",
        "contact_email": CONTACT_EMAIL,
        "fallback_email": FALLBACK_EMAIL,
        "pinakes_url": PINAKES_URL,
        "auditor_url": AUDITOR_URL,
        "github_url": GITHUB_URL,
        "redaction_url": REDACTION_URL,
        "cov": coverage(),
    }


@app.after_request
def cache_static(response):
    # Fonts and images are content-stable: regenerating them means a new
    # filename, so a year is safe and it keeps the machine idle.
    if request.path.startswith("/static/") and any(
            request.path.endswith(ext) for ext in
            (".woff2", ".avif", ".webp", ".png", ".svg")):
        # Assign rather than setdefault: Flask's static handler has already set
        # a Cache-Control, so setdefault would silently lose.
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@app.after_request
def security_headers(response):
    # Written out deliberately. Pinakes' own CSP omits the host serving its design
    # tokens, so tokens.css is refused on every page load there; here the tokens are
    # served from this origin and 'self' covers them.
    response.headers.setdefault("Content-Security-Policy", "; ".join([
        "default-src 'self'",
        # Everything is served from this origin — the four webfonts included —
        # so no third-party host appears here at all.
        "style-src 'self'",
        "font-src 'self'",
        "img-src 'self' data:",
        "script-src 'self'",
        "connect-src 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
    ]))
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Strict-Transport-Security",
                                "max-age=31536000; includeSubDomains")
    return response


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.before_request
def canonical_host():
    """Send www to the apex, so the site has one address rather than two."""
    if CANONICAL_HOST and request.host.startswith("www."):
        return redirect(request.url.replace("://www.", "://", 1), code=301)
    return None


@app.route("/")
def landing():
    return render_template("index.html", page="landing")


@app.route("/how")
def how():
    return render_template("how.html", page="how")


@app.route("/eunomia-and-pinakes")
def pinakes():
    return render_template("pinakes.html", page="pinakes")


@app.route("/start", methods=["GET", "POST"])
def start():
    if request.method == "GET":
        return render_template("start.html", page="start", errors={}, values={})

    # Honeypot. Not named "website": a password manager or form-fill profile can
    # recognise that name and fill it in for a real person, whose submission then
    # vanishes behind the thank-you page. The log line makes a false positive
    # recoverable rather than invisible.
    if request.form.get("eu_confirm", "").strip():
        app.logger.info("Honeypot tripped from %s; submission dropped.", client_id())
        return redirect(url_for("thanks"))

    # Build values before the rate check, so a throttled response redisplays the
    # form exactly as an invalid one does. request.form is a MultiDict and has no
    # hoping_for_list, which silently unchecked every box on this branch.
    values = {k: request.form.get(k, "").strip() for k in
              ("name", "email", "journal", "archive_url", "role", "standing", "notes")}

    # Collapse CR/LF and tabs in everything that reaches an email header. strip()
    # only removes surrounding whitespace, and an interior newline would make
    # EmailMessage raise — after the row had already been committed.
    for key in ("name", "email", "journal", "archive_url", "role", "standing"):
        values[key] = " ".join(values[key].split())

    chosen = request.form.getlist("hoping_for")
    values["hoping_for"] = ", ".join(chosen)
    values["hoping_for_list"] = chosen
    values["wants_call"] = bool(request.form.get("wants_call"))

    client = rate_key(client_id())
    if rate_limited(client, "attempt"):
        return render_template(
            "start.html", page="start", values=values, errors={},
            rate_limited=True,
        ), 429

    errors = {}
    if not values["name"]:
        errors["name"] = "I need a name to write back to."
    if "@" not in values["email"] or "." not in values["email"].split("@")[-1]:
        errors["email"] = ("That email address doesn't look complete — it needs an @ "
                           "and a domain after it, like name@university.edu.")
    if not values["journal"]:
        errors["journal"] = "Which journal are you writing about?"
    if not values["archive_url"]:
        errors["archive_url"] = "I need a link to your archive to be able to tell you anything useful."

    if errors:
        return render_template("start.html", page="start", errors=errors, values=values), 400

    if rate_limited(client, "accepted"):
        return render_template(
            "start.html", page="start", values=values, errors={},
            rate_limited=True,
        ), 429

    try:
        store(values)
    except (sqlite3.Error, OSError):
        # OSError as well as sqlite3.Error: db() calls mkdir and connect before
        # any sqlite exception can be raised, so an unwritable volume — the exact
        # failure this guard exists for — arrives as PermissionError.
        app.logger.exception("Could not store submission.")
        notify(values)  # last chance not to lose it; notify swallows its own errors
        return render_template(
            "start.html", page="start", values=values, errors={},
            store_failed=True,
        ), 500

    notify(values)
    auto_reply(values)
    return redirect(url_for("thanks"))


@app.route("/start/thanks")
def thanks():
    return render_template("thanks.html", page="start")


@app.route("/robots.txt")
def robots():
    return send_from_directory(app.static_folder, "robots.txt", mimetype="text/plain")


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html", page=None), 404


@app.errorhandler(413)
def too_large(_error):
    # request.form is unreadable once the limit trips, so their text is gone.
    # Say so, and give them somewhere to send it.
    return render_template(
        "start.html", page="start", values={}, errors={}, too_large=True,
    ), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=True)
