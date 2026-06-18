# Deploying Modmail to Oracle Cloud

This guide moves your Modmail bot (this fork) and the Logviewer onto an Oracle
Cloud **Always Free** VM, while continuing to use your **existing MongoDB**. The
logviewer is published on your own domain via a **Cloudflare Tunnel**, so no
inbound ports are exposed.

What you get:
- `bot` — built from this repo's `Dockerfile`, so your fork's changes are
  included and the image is native to the VM's architecture.
- `logviewer` — the web UI for closed-thread log links.
- `cloudflared` — a Cloudflare Tunnel that serves the logviewer at your domain
  over HTTPS, with no open ports on the VM.
- No database container — the bot and logviewer both point at your current
  `CONNECTION_URI`.

---

## 1. Create the VM

In the [OCI Console](https://cloud.oracle.com/) → **Compute → Instances → Create**:

- **Image:** Canonical Ubuntu 22.04 (or Oracle Linux 9).
- **Shape:** either Always Free option works:
  - `VM.Standard.A1.Flex` (Ampere ARM) — more RAM, but see the logviewer ARM
    note under Troubleshooting.
  - `VM.Standard.E2.1.Micro` (x86, 1 OCPU / 1 GB RAM) — logviewer runs natively;
    `setup.sh` adds a swap file to handle the 1 GB limit during image builds.
- **SSH keys:** upload/download a key pair so you can log in.

With a Cloudflare Tunnel you do **not** need to open any ingress ports in the OCI
Security List — the tunnel connects outbound. (Port `22` for SSH is open by
default.)

## 2. Create the Cloudflare Tunnel

In the [Cloudflare Zero Trust dashboard](https://one.dash.cloudflare.com/) →
**Networks → Tunnels**:

1. **Create a tunnel** → choose **Cloudflared** → give it a name (e.g. `modmail`).
2. On the install screen, **copy the tunnel token** — it's the long string in the
   shown `cloudflared ... run <TOKEN>` command. You don't run that command; the
   `cloudflared` container uses the token. Save it for step 4.
3. Add a **Public Hostname**:
   - **Subdomain / Domain:** e.g. `logs` + your Cloudflare-managed domain.
   - **Type:** `HTTP`
   - **URL:** `caddy:8080`  (the auth-proxy edge — **not** the logviewer
     directly, so every request goes through the Discord role check)
4. Save. Cloudflare auto-creates the DNS record and HTTPS cert for that hostname.

## 3. Install Docker on the VM

SSH in, then:

```bash
ssh ubuntu@YOUR_VM_PUBLIC_IP        # or opc@... on Oracle Linux

# Get this fork's deploy files:
git clone https://github.com/PloverRoblox/modmail.git
cd modmail
git checkout claude/gifted-curie-z2wprx
cd deploy/oracle

chmod +x setup.sh && ./setup.sh
```

Then **log out and back in** so your user picks up the `docker` group.

## 4. Configure your environment

```bash
cp .env.example .env
nano .env
```

Fill in:
- `TOKEN`, `GUILD_ID`, `OWNERS` — same values as your old host.
- `CONNECTION_URI` — your **existing** MongoDB URI (nothing migrates; the bot
  just reconnects to the same database).
- `LOG_URL` — your tunnel hostname, e.g. `https://logs.yourdomain.com`
- `TUNNEL_TOKEN` — the token you copied in step 2.
- The `DISCORD_*`, `REQUIRED_ROLE_ID`, and `SESSION_SECRET` values — see the next
  step.

## 4b. Lock the logs behind Discord (role-gated)

The logs are protected by a small Discord OAuth2 proxy (`authproxy` + `caddy`):
only members of `GUILD_ID` who hold `REQUIRED_ROLE_ID` can view them.

1. In the [Discord Developer Portal](https://discord.com/developers/applications)
   → your application → **OAuth2**:
   - Copy the **Client ID** and **Client Secret** into `DISCORD_CLIENT_ID` /
     `DISCORD_CLIENT_SECRET`.
   - Under **Redirects**, add **exactly**:
     `https://<your-log-domain>/auth/callback`
     (e.g. `https://pebble.getplover.com/auth/callback`) and **Save Changes**.
2. In `.env`, set:
   - `DISCORD_REDIRECT_URI` to that same `…/auth/callback` URL.
   - `REQUIRED_ROLE_ID` to the role ID allowed to view logs.
   - `GUILD_ID` is reused from the bot config above.
   - `SESSION_SECRET` to a random string: `openssl rand -hex 32`.

The proxy requests the `identify` and `guilds.members.read` scopes — the latter
is what lets it read the visitor's roles in your server. No bot invite or extra
permissions are needed.

## 5. Launch

```bash
docker compose up -d --build
docker compose logs -f bot          # watch it connect to Discord
docker compose logs cloudflared     # should show "Registered tunnel connection"
```

Open `https://logs.yourdomain.com` in a browser — you'll be sent to Discord to
log in, and only granted through if you hold the required role. Closed-thread log
links will now use that domain.

## 6. Decommission the old host

Once the new instance is confirmed working, stop the bot on your previous host
so two instances don't run against the same database at once.

---

## Updating later

```bash
cd ~/modmail && git pull
cd deploy/oracle && docker compose up -d --build
```

## Troubleshooting

- **Bot won't start / DB errors:** double-check `CONNECTION_URI` and that your
  MongoDB/Atlas network access list (Atlas → Network Access) allows the VM's
  public IP.
- **Logviewer domain shows Cloudflare error 502/1033:** the tunnel can't reach
  the edge. Confirm the Public Hostname URL is exactly `caddy:8080`, and that
  `docker compose logs cloudflared` shows a registered connection.
- **Discord login loops or "Invalid OAuth2 redirect_uri":** the redirect in the
  Developer Portal must match `DISCORD_REDIRECT_URI` exactly, including the
  `https://` and the `/auth/callback` path.
- **"You do not have the required role":** the logged-in user lacks
  `REQUIRED_ROLE_ID` in `GUILD_ID`, or those IDs are wrong. Check
  `docker compose logs authproxy`.
- **`cloudflared` keeps restarting:** the `TUNNEL_TOKEN` is wrong or missing —
  re-copy it from the tunnel's install screen.
- **Logviewer container exits with "exec format error" on the ARM VM:** the
  upstream `logviewer` image may not publish an `arm64` variant. Either add
  `platform: linux/amd64` under the `logviewer` service (with
  `sudo apt install -y qemu-user-static binfmt-support`), or use the
  `VM.Standard.E2.1.Micro` x86 shape so the image runs natively.
