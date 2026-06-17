# Deploying Modmail to Oracle Cloud

This guide moves your Modmail bot (this fork) and the Logviewer onto an Oracle
Cloud **Always Free** VM, while continuing to use your **existing MongoDB**.

What you get:
- `bot` — built from this repo's `Dockerfile`, so your fork's changes are
  included and the image is native to the VM's ARM64 architecture.
- `logviewer` — the web UI for closed-thread log links, served on port `8000`.
- No database container — the bot and logviewer both point at your current
  `CONNECTION_URI`.

---

## 1. Create the VM

In the [OCI Console](https://cloud.oracle.com/) → **Compute → Instances → Create**:

- **Image:** Canonical Ubuntu 22.04 (or Oracle Linux 9).
- **Shape:** `VM.Standard.A1.Flex` (Ampere ARM, **Always Free** — e.g. 1–2 OCPUs,
  6–12 GB RAM is plenty).
- **SSH keys:** upload/download a key pair so you can log in.
- Note the instance's **public IP** after it boots.

## 2. Open the firewall (cloud side)

The instance firewall is handled by `setup.sh`, but the cloud network is separate.

In the OCI Console → **Networking → Virtual Cloud Networks → your VCN → your
subnet → Security List → Add Ingress Rules**:

| Source CIDR | Protocol | Dest. Port | Purpose       |
|-------------|----------|------------|---------------|
| `0.0.0.0/0` | TCP      | `8000`     | Logviewer     |

(Port `22` for SSH is usually open by default.)

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
- `LOG_URL` — `http://YOUR_VM_PUBLIC_IP:8000`

## 5. Launch

```bash
docker compose up -d --build
docker compose logs -f bot        # watch it connect to Discord
```

You should see the bot log in. Closed-thread log links will resolve at
`http://YOUR_VM_PUBLIC_IP:8000`.

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
  MongoDB/Atlas network access list allows the VM's public IP.
- **Logviewer container exits with "exec format error" on the ARM VM:** the
  upstream `logviewer` image may not publish an `arm64` variant. Two fixes:
  1. Add emulation, then retry:
     `sudo apt install -y qemu-user-static binfmt-support` and add
     `platform: linux/amd64` under the `logviewer` service in
     `docker-compose.yml`; **or**
  2. Use an x86 shape (`VM.Standard.E2.1.Micro`, also Always Free) for the VM so
     the upstream image runs natively.
- **Can't reach the logviewer in a browser:** confirm both the OCI Security List
  rule (step 2) *and* the instance firewall (`setup.sh`) allow port `8000`.
```
