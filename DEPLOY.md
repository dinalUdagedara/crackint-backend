# Deploying to Oracle Cloud "Always Free"

Free-forever alternative to the old AWS ECS/RDS/ALB/NAT setup (which was the source of the
~$100/mo bill). Everything — FastAPI backend, Postgres, HTTPS — runs on a single Oracle
Ampere A1 VM (4 OCPU / 24GB RAM, Always Free tier, no time limit, no card charged as long as
you stay within Always Free shapes).

Domain used below: `api.dinaludagedara.com` (managed in Namecheap).

---

## 1. Create the Oracle Cloud account + VM

1. Sign up at [cloud.oracle.com](https://cloud.oracle.com) (requires a card for identity
   verification, but Always Free resources are never billed — set a budget alert anyway, see
   step 6).
2. Console → **Compute → Instances → Create Instance**.
3. **Image and shape**:
   - Image: **Canonical Ubuntu 22.04**
   - Shape: **VM.Standard.A1.Flex** (Ampere/ARM) — set **4 OCPUs / 24GB RAM** (the max
     Always Free allows). If your region shows "Out of capacity" for A1, try a different
     Availability Domain, or retry over the next day or two — this is a known Oracle Free Tier
     quirk, not a config issue.
4. **Networking**: use the default VCN, "Assign a public IPv4 address" — leave checked.
5. **SSH keys**: let Oracle generate a key pair, download the private key
   (`ssh-key-....key`) — you'll need it below. Save it somewhere safe, e.g.
   `~/.ssh/oracle-crackint.key`.
6. Create the instance, wait for it to go **Running**, note its **public IP**.
7. **Billing safety net** (since this is exactly what went wrong last time): Console →
   **Billing → Budgets** → create a budget of ~$1 with an email alert at 100%. On Always Free
   shapes this should never trigger, but it means you'll know immediately if anything
   non-free gets provisioned by mistake.

## 2. Open firewall ports (80, 443)

Oracle blocks traffic by default at the **Security List** level (in addition to the OS
firewall).

1. Console → your instance → **Subnet** link → **Security Lists** → default security list.
2. **Add Ingress Rules** twice:
   - Source CIDR `0.0.0.0/0`, IP Protocol TCP, Destination Port `80`
   - Source CIDR `0.0.0.0/0`, IP Protocol TCP, Destination Port `443`
3. SSH (port 22) is already open by default.

## 3. Point your domain at the VM (Namecheap)

Namecheap → Domain List → `dinaludagedara.com` → **Manage** → **Advanced DNS** → **Add New
Record**:

| Type | Host | Value          | TTL       |
|------|------|----------------|-----------|
| A    | api  | `<VM_PUBLIC_IP>` | Automatic |

DNS propagation is usually minutes, occasionally up to an hour. Check with:

```bash
dig +short api.dinaludagedara.com
```

It should print the VM's IP once propagated.

## 4. Set up the VM

SSH in (Ubuntu's default user is `ubuntu`):

```bash
ssh -i ~/.ssh/oracle-crackint.key ubuntu@<VM_PUBLIC_IP>
```

Install Docker + the OS firewall rule (Oracle's Ubuntu images also run `iptables`/`netfilter`
locally, on top of the cloud Security List from step 2):

```bash
# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker

# Allow 80/443 through the VM's own firewall
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || sudo apt-get install -y iptables-persistent
```

## 5. Deploy the app

From your Mac, clone/push this repo to GitHub first (see step 7 below if not done yet), then
on the VM:

```bash
git clone https://github.com/<your-username>/crackint-backend.git
cd crackint-backend
cp .env.production.example .env
nano .env   # fill in real values (OpenAI key, DB password, JWT secret, etc.)
```

Edit `Caddyfile` if your domain differs from `api.dinaludagedara.com` (it already matches, so
nothing to change if you're following this doc as-is).

Bring the stack up:

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

First build will take several minutes (torch/transformers). Watch it:

```bash
docker compose -f docker-compose.prod.yml logs -f backend
```

You should see the Alembic migrations run, both NER models load, and Uvicorn start — same
output verified locally before deploying here.

Caddy will automatically request a Let's Encrypt certificate for `api.dinaludagedara.com` the
first time it gets a request on port 80/443 — this only works once DNS (step 3) has actually
propagated to the VM's IP.

## 6. Verify

```bash
curl https://api.dinaludagedara.com/api/v1/health
# {"status":"ok"}
```

Also check `https://api.dinaludagedara.com/api/v1/docs` in a browser for the Swagger UI.

## 7. Point the frontend at the new backend

In `crackint-frontend/.env.local` (and wherever it's deployed, e.g. Vercel project env vars):

```
NEXT_PUBLIC_API_URL=https://api.dinaludagedara.com
```

Redeploy the frontend.

## 8. Redeploying after code changes

```bash
ssh -i ~/.ssh/oracle-crackint.key ubuntu@<VM_PUBLIC_IP>
cd crackint-backend
git pull
docker compose -f docker-compose.prod.yml up --build -d
```

## 9. Backups

Postgres data lives in the `pgdata` Docker volume on the VM — nothing is backed up off-box by
default. Periodically dump it somewhere durable (e.g. your own machine, or Oracle's free 20GB
Object Storage):

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U crackint crackint_db > backup-$(date +%F).sql
```

## What NOT to add back

The old ~$100/mo bill came from ECS/Fargate + RDS + an Application Load Balancer + a NAT
Gateway all running 24/7. None of those exist in this setup — it's a single always-free VM,
self-hosted Postgres, and Caddy doing TLS for free via Let's Encrypt. If you ever go back to
AWS for something, avoid NAT Gateways and ALBs for low-traffic services — they bill hourly
regardless of usage and are the single biggest source of "surprise" AWS bills for small apps.
