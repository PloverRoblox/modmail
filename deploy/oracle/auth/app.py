"""Discord OAuth2 forward-auth proxy for the Modmail logviewer.

Sits behind Caddy's `forward_auth`. Visitors are sent through Discord's OAuth2
flow; only members of GUILD_ID who hold REQUIRED_ROLE_ID are issued a signed
session cookie and allowed through to the logviewer.

Endpoints (all under /auth, routed straight to this service by Caddy):
  /auth/verify    - called by Caddy for every request; 200 if authed, else 302 to login
  /auth/login     - starts the Discord OAuth2 flow
  /auth/callback  - Discord redirects here; verifies role, sets session cookie
  /auth/logout    - clears the session cookie
"""

import os
import time
import secrets
import urllib.parse

import requests
from flask import Flask, request, redirect, make_response
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

CLIENT_ID = os.environ["DISCORD_CLIENT_ID"]
CLIENT_SECRET = os.environ["DISCORD_CLIENT_SECRET"]
REDIRECT_URI = os.environ["DISCORD_REDIRECT_URI"]  # https://<domain>/auth/callback
GUILD_ID = os.environ["GUILD_ID"]
REQUIRED_ROLE_ID = os.environ["REQUIRED_ROLE_ID"]
SECRET_KEY = os.environ["SESSION_SECRET"]

COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "modmail_logs_session")
SESSION_TTL = int(os.environ.get("SESSION_TTL", "86400"))  # 24h

API_BASE = "https://discord.com/api"
SCOPES = "identify guilds.members.read"

app = Flask(__name__)
session_signer = URLSafeTimedSerializer(SECRET_KEY, salt="modmail-logs-session")
state_signer = URLSafeTimedSerializer(SECRET_KEY, salt="modmail-logs-state")


def _redirect_to_login():
    """Send the browser into Discord's OAuth2 flow, remembering where it wanted to go."""
    original = request.headers.get("X-Forwarded-Uri", "/")
    state = state_signer.dumps({"nonce": secrets.token_urlsafe(8), "dest": original})
    params = urllib.parse.urlencode(
        {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "state": state,
        }
    )
    return redirect(f"{API_BASE}/oauth2/authorize?{params}")


@app.route("/auth/verify")
def verify():
    token = request.cookies.get(COOKIE_NAME)
    if token:
        try:
            session_signer.loads(token, max_age=SESSION_TTL)
            return ("", 200)
        except (BadSignature, SignatureExpired):
            pass
    return _redirect_to_login()


@app.route("/auth/login")
def login():
    return _redirect_to_login()


@app.route("/auth/callback")
def callback():
    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state:
        return ("Missing code or state.", 400)
    try:
        state_data = state_signer.loads(state, max_age=600)
    except (BadSignature, SignatureExpired):
        return ("Invalid or expired login attempt. Please try again.", 400)

    # Exchange the authorization code for an access token.
    token_resp = requests.post(
        f"{API_BASE}/oauth2/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    if token_resp.status_code != 200:
        return ("Discord token exchange failed.", 403)
    access_token = token_resp.json().get("access_token")

    # Read the caller's member object for the guild (includes their role IDs).
    member_resp = requests.get(
        f"{API_BASE}/users/@me/guilds/{GUILD_ID}/member",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if member_resp.status_code != 200:
        return ("You are not a member of the required server.", 403)
    member = member_resp.json()
    if REQUIRED_ROLE_ID not in member.get("roles", []):
        return ("You do not have the required role to view these logs.", 403)

    # Authorised: issue a signed session cookie and return to the original page.
    user_id = member.get("user", {}).get("id")
    value = session_signer.dumps({"id": user_id, "ts": int(time.time())})
    dest = state_data.get("dest", "/")
    if not dest.startswith("/"):
        dest = "/"
    resp = make_response(redirect(dest))
    resp.set_cookie(
        COOKIE_NAME, value, max_age=SESSION_TTL, httponly=True, secure=True, samesite="Lax"
    )
    return resp


@app.route("/auth/logout")
def logout():
    resp = make_response(redirect("/auth/login"))
    resp.delete_cookie(COOKIE_NAME)
    return resp
