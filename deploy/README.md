# FinDesk private server deployment

The production branch includes the desktop and mobile commits. Authentication maps the
configured owner account to one private user workspace; this deployment is a personal instance. The web port binds to loopback;
the database, cache and API have no published ports. It does not copy local financial data.

## Prepare and run

1. Create `deploy/production.env` using `production.env.example`, and set a random hexadecimal database password.
2. Create `deploy/backend.env` using `backend/.env.example`, and configure the required provider keys.
   Keep secrets on the destination host. Do not commit either file.
3. Build images for the destination architecture (myserver is Linux amd64):

```sh
docker build --platform linux/amd64 -t findesk-backend:v1 backend
docker build --platform linux/amd64 -f web/Dockerfile.production -t findesk-web:v1 web
```

Transfer the images and repository deployment files to a dedicated server directory.
On the server, run:

```sh
docker compose --env-file deploy/production.env -f compose.production.yml up -d --no-build
curl --fail http://127.0.0.1:18080/api/health
```

Open the private instance through an SSH tunnel from your computer:

```sh
ssh -N -L 18080:127.0.0.1:18080 myserver
```

Visit `http://localhost:18080`. This is a fresh database. Upload a statement only after
checking the destination instance. Do not reuse local Docker volumes as production volumes.

## Domain, Caddy and mobile access

The production domain is `findesk.suertexu.com`. Its Cloudflare `A` record was verified on
2026-09-07. Keep it DNS-only during the first validation; the server address is intentionally
not committed to this repository.

myserver already runs Caddy 2.11 in Docker on ports 80/443. The production web service joins
the existing external `caddy_default` network with the unique alias `findesk-web`. Copy the
site block from `deploy/Caddyfile.findesk.example` into `/data/caddy/Caddyfile` after the
application login has been configured and verified through the loopback port.

Production authentication is fail-closed. Generate a one-time setup code inside the backend
image. Store only the printed `AUTH_SETUP_TOKEN_HASH` line in `deploy/backend.env`; keep the
raw setup code in your password manager until registration is complete:

```sh
docker compose --env-file deploy/production.env -f compose.production.yml run --rm \
  backend python -m app.auth.setup_token
docker exec caddy caddy validate --config /etc/caddy/Caddyfile
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

Keep `deploy/backend.env` at mode `600`, start the application, and use the raw setup code on
the registration page to choose the owner email and password. The database accepts exactly
one owner row, so every later registration attempt is rejected atomically. After setup, set
`AUTH_ALLOW_INITIAL_REGISTRATION=false` in `deploy/production.env`, remove
`AUTH_SETUP_TOKEN_HASH` from `deploy/backend.env`, and restart the services.

The application uses an opaque HttpOnly/Secure/SameSite cookie, server-side revocable
sessions, CSRF tokens for writes and bounded login attempts. There is no ongoing public
registration; the setup screen exists only before the first owner is created.

The UI uses same-origin `/api`, including streaming responses. Nginx disables response
buffering and permits a 25 MB request body. The backend may impose tighter file limits.
The development Vite server is not used in production.

## Backups and rollback

Before upgrades, save a `pg_dump -Fc -U findesk findesk` from the db container and a copy of
the imports volume to a protected backup location. A complete backup needs both database
and original statements. Test restoration into separate volumes before relying on it.
Use distinct image version tags; roll back by restoring the prior version in production.env
and recreating services. If a schema change is incompatible, restore its matching backup
into separate volumes before switching. Never use `down -v` against the live instance.

## Read-only server assessment (2026-09-07)

Docker is installed; architecture is amd64. The production containers were built and started
behind the loopback port on 2026-09-07; the health check passed. Free disk was about 4.7 GB
(92% used) afterward, so Docker build cache should be reviewed before future builds. The
public Caddy route remains disabled until application credentials are configured and tested.

## Validation

The frontend suite passes 23/23 tests and Vite production build succeeds. The backend suite
passes 601/601 tests, including registration, login, CSRF and statement-import coverage. The frontend
production dependency audit reports zero known vulnerabilities. Compose validates with
`config --no-interpolate --no-env-resolution --quiet` (syntax only, not runtime secrets).
Both production images built successfully on myserver, and the Nginx-to-backend health check
passed through `http://127.0.0.1:18080/api/health`.
