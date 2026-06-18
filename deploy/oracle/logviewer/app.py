__version__ = "1.1.3-pebble"

# Pebble customisation of the Modmail logviewer (AGPL-3.0).
# Based on the upstream app.py; the home route ("/") is replaced with a
# searchable / filterable / paginated history browser over the logs collection.
# Everything else (raw + html log rendering) is unchanged.

import html
import math
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

import dateutil.parser
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from natural.date import duration
from sanic import Sanic, response
from sanic.exceptions import NotFound
from jinja2 import Environment, FileSystemLoader

from core.models import LogEntry

load_dotenv()

if "URL_PREFIX" in os.environ:
    print("Using the legacy config var `URL_PREFIX`, rename it to `LOG_URL_PREFIX`")
    prefix = os.environ["URL_PREFIX"]
else:
    prefix = os.getenv("LOG_URL_PREFIX", "/logs")

if prefix == "NONE":
    prefix = ""

PER_PAGE = 25

MONGO_URI = os.getenv("MONGO_URI") or os.getenv("CONNECTION_URI")
if not MONGO_URI:
    print("No CONNECTION_URI config var found. "
          "Please enter your MongoDB connection URI in the configuration or .env file.")
    exit(1)

app = Sanic(__name__)
app.static("/static", "./static")

jinja_env = Environment(loader=FileSystemLoader("templates"))


def render_template(name, *args, **kwargs):
    template = jinja_env.get_template(name + ".html")
    return response.html(template.render(*args, **kwargs))


app.ctx.render_template = render_template


def strtobool(val):
    val = val.lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return 1
    elif val in ('n', 'no', 'f', 'false', 'off', '0'):
        return 0
    else:
        raise ValueError("invalid truth value %r" % (val,))


@app.listener("before_server_start")
async def init(app, loop):
    app.ctx.db = AsyncIOMotorClient(MONGO_URI).modmail_bot
    use_attachment_proxy = strtobool(os.getenv("USE_ATTACHMENT_PROXY", "no"))
    if use_attachment_proxy:
        app.ctx.attachment_proxy_url = os.getenv("ATTACHMENT_PROXY_URL", "https://cdn.discordapp.xyz")
        app.ctx.attachment_proxy_url = html.escape(app.ctx.attachment_proxy_url).rstrip("/")
    else:
        app.ctx.attachment_proxy_url = None


@app.exception(NotFound)
async def not_found(request, exc):
    return render_template("not_found")


def _int_arg(request, name, default):
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


@app.get("/")
async def index(request):
    """History browser: searchable, filterable, paginated list of all logs."""
    db = app.ctx.db

    q = (request.args.get("q") or "").strip()
    status = request.args.get("status", "all")
    if status not in ("all", "open", "closed"):
        status = "all"
    page = max(1, _int_arg(request, "page", 1))

    match = {}
    if status == "open":
        match["open"] = True
    elif status == "closed":
        match["open"] = False

    if q:
        esc = re.escape(q)
        ors = [
            {"recipient.name": {"$regex": esc, "$options": "i"}},
            {"key": {"$regex": esc, "$options": "i"}},
        ]
        if q.isdigit():
            ors.append({"recipient.id": q})
            ors.append({"recipient.id": int(q)})
        match["$or"] = ors

    total = await db.logs.count_documents(match)
    total_pages = max(1, math.ceil(total / PER_PAGE))
    page = min(page, total_pages)
    skip = (page - 1) * PER_PAGE

    pipeline = [
        {"$match": match},
        {"$sort": {"created_at": -1}},
        {"$skip": skip},
        {"$limit": PER_PAGE},
        {"$project": {
            "key": 1, "open": 1, "created_at": 1, "recipient": 1,
            "message_count": {"$size": {"$ifNull": ["$messages", []]}},
        }},
    ]
    docs = await db.logs.aggregate(pipeline).to_list(length=PER_PAGE)

    now = datetime.now(timezone.utc)
    entries = []
    for doc in docs:
        recipient = doc.get("recipient") or {}
        try:
            created = dateutil.parser.parse(doc["created_at"]).astimezone(timezone.utc)
            created_human = created.strftime("%b %d, %Y · %H:%M UTC")
            ago = duration(created, now=now)
        except Exception:
            created_human, ago = "", ""
        entries.append({
            "key": doc["key"],
            "open": doc.get("open", False),
            "recipient_name": recipient.get("name", "Unknown"),
            "recipient_id": recipient.get("id", ""),
            "recipient_avatar": recipient.get("avatar_url", ""),
            "created": created_human,
            "ago": ago,
            "message_count": doc.get("message_count", 0),
        })

    # Logged-in user, forwarded by the Discord auth proxy via Caddy headers.
    current_user = None
    cu_id = request.headers.get("X-Auth-Id")
    if cu_id:
        current_user = {
            "id": cu_id,
            "name": urllib.parse.unquote(request.headers.get("X-Auth-Name") or "User"),
            "avatar": urllib.parse.unquote(request.headers.get("X-Auth-Avatar") or ""),
        }

    # Who's online: staff with a logviewer session seen in the last 5 minutes.
    online = []
    cutoff = now - timedelta(minutes=5)
    async for u in db.pebble_online.find({"last_seen": {"$gte": cutoff}}).sort("name", 1):
        online.append({
            "id": str(u.get("user_id", "")),
            "name": u.get("name", "User"),
            "avatar": u.get("avatar", ""),
        })

    return render_template(
        "index",
        entries=entries,
        q=q,
        status=status,
        page=page,
        total=total,
        total_pages=total_pages,
        prefix=prefix,
        current_user=current_user,
        online=online,
    )


@app.get(prefix + "/raw/<key>")
async def get_raw_logs_file(request, key):
    """Returns the plain text rendered log entry"""
    document = await app.ctx.db.logs.find_one({"key": key})

    if document is None:
        raise NotFound

    log_entry = LogEntry(app, document)

    return log_entry.render_plain_text()


@app.get(prefix + "/<key>")
async def get_logs_file(request, key):
    """Returns the html rendered log entry"""
    document = await app.ctx.db.logs.find_one({"key": key})

    if document is None:
        raise NotFound

    log_entry = LogEntry(app, document)

    return log_entry.render_html()


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        debug=bool(os.getenv("DEBUG", False)),
    )
