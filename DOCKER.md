# Odoo 20.0 — Docker Deployment

Production-grade container layout for running Odoo on a single host.

## Layout

| File                  | Purpose                                                     |
| --------------------- | ----------------------------------------------------------- |
| `Dockerfile`          | Builds the Odoo server image (Ubuntu 24.04 Noble, Py 3.12). |
| `entrypoint.sh`       | Waits for Postgres, renders `odoo.conf`, bootstraps DB.    |
| `docker-compose.yml`  | Two-service stack: `db` (Postgres 16) + `odoo`.             |
| `odoo.conf.example`   | Reference Odoo server config; mount to `/etc/odoo/odoo.conf`. |
| `.dockerignore`       | Keeps `docker build` context lean.                          |

## Quick start

```bash
# 1. Set a strong admin password (and override the default DB creds).
export ODOO_ADMIN_PASSWD="$(openssl rand -hex 16)"
export POSTGRES_PASSWORD="$(openssl rand -hex 16)"

# 2. Build the image and start the stack.
docker compose up -d --build

# 3. Watch logs until "Odoo is up and running" appears.
docker compose logs -f odoo

# 4. Open the web UI:
#    http://localhost:8069
#    Login: admin / ${ODOO_ADMIN_PASSWD}
```

## How the database is created

On first start, `entrypoint.sh` detects that `${ODOO_DB}` does not yet exist
on the Postgres host and runs:

```bash
odoo-bin -c /etc/odoo/odoo.conf \
  -d "${ODOO_DB}" -i base --stop-after-init
```

Subsequent restarts just exec `odoo-bin`. To force a module install/upgrade
on next start, set:

```bash
ODOO_INIT_MODULES="sale,stock"        # first-run only (won't overwrite an existing DB)
ODOO_UPDATE_MODULES="account,sale"   # reruns -u every time the container starts
```

## Mounting custom addons

```bash
mkdir -p ./extra-addons
echo "./extra-addons:/opt/odoo/src/extra-addons" >> docker-compose.override.yml
docker compose up -d
```

…then in your mounted `odoo.conf`, add
`/opt/odoo/src/extra-addons` to `addons_path`.

## Switching to the upstream image

If you'd rather not build locally, comment out the `build:` block in
`docker-compose.yml` and uncomment `image: odoo:20.0`. The upstream image
already ships its own `entrypoint` with similar conventions — read its docs
if you want to align env var names.

## Production tuning

| Variable             | Dev default | Production recommendation                     |
| -------------------- | ----------- | -------------------------------------------- |
| `ODOO_WORKERS`       | `0`         | `(2 * CPU cores) + 1`, cap at ~`16`          |
| `ODOO_MAX_CRON_THREADS` | `2`      | `2`                                          |
| `ODOO_LIMIT_MEMORY_SOFT` | `2147483648` | match `workers * ~1.2 GiB`              |
| `POSTGRES_PASSWORD`  | `odoo`      | long random — must match `docker-compose.yml`'s `${POSTGRES_PASSWORD}`. |

Also front the container with a TLS proxy (Traefik, Caddy, nginx) and
enable `proxy_mode = True` in `odoo.conf`.

## Backing up

```bash
# Database dump
docker compose exec db pg_dump -U odoo odoo > "$(date +%F)-odoo.sql"

# Filestore (uploads, attachments)
docker run --rm -v odoo_odoo-data:/data -v "$PWD":/backup \
    alpine tar czf /backup/odoo-filestore.tgz -C /data .
```

## Tearing down

```bash
docker compose down           # stop, keep volumes
docker compose down -v        # stop AND wipe DB + filestore (destructive)
```
