# FinDesk private server deployment

The production branch includes the desktop and mobile commits. The public app still uses
one `demo` user; this deployment is a personal instance. The web port binds to loopback;
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

## Existing Caddy and mobile access

myserver already runs Caddy in Docker on ports 80/443. Choose a domain and configure
authentication for the whole site before adding its route. A Caddy container cannot reach
another container through `127.0.0.1`; connect it to the application's Docker network and
proxy to the web service, or explicitly configure a host gateway. Keep all API paths behind
the same authentication. Validate the Caddy configuration before reloading it.

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

Docker is installed; architecture is amd64. Available memory was about 2.3 GB; free disk
about 6.4 GB (89% used). Build images locally and check disk again before image transfer.
No server files, domains, containers or credentials were changed during this assessment.
Remote rollout awaits the destination domain/access choice and provider configuration.

## Validation

The frontend suite passes 20/20 tests and Vite production build succeeds. Compose validates
with `config --no-interpolate --no-env-resolution --quiet` (syntax only, not runtime secrets).
The local production-image build could not pull `node:22-alpine`: Docker Hub returned EOF
before build execution. Image runtime and Nginx proxy smoke tests remain pending.
