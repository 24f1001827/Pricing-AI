# No-cost deployment: Oracle Always Free + Cloudflare Pages

This setup keeps automated retraining by running the API and its scheduler on one always-on Oracle Cloud Always Free VM. It is suitable for a small public beta, not a service with uptime or backup guarantees.

## What is deployed

| Component | Location | Notes |
| --- | --- | --- |
| Vue frontend | Cloudflare Pages | HTTPS and global static hosting |
| FastAPI API | Oracle Always Free VM | Reached through Caddy over HTTPS |
| Scheduler | Oracle Always Free VM | Dedicated container; runs the nightly evaluation at 23:30 Asia/Kolkata |
| PostgreSQL | Oracle Always Free VM | Docker volume, not publicly exposed |
| MLflow + training artifacts | Oracle Always Free VM | Docker volume, not publicly exposed |

## 1. Create the VM

1. Create an Oracle Cloud Always Free Ampere A1 VM in your home region. Use Ubuntu and allocate at least 2 OCPUs and 12 GB RAM if capacity is available.
2. In the Oracle network security list, permit inbound TCP `22` from your IP and TCP `80`/`443` from the internet. Do **not** expose FastAPI (`8000`), Postgres (`5432`), or MLflow (`5000`).
3. SSH into the VM and install Docker Engine and the Docker Compose plugin.
4. Clone this project privately onto the VM. Do not copy your existing `.env` files.

## 2. Configure secrets

1. Copy `backend/.env.example` to `backend/.env`.
2. Set `POSTGRES_PASSWORD` in `backend/.env`; use a long random value.
3. Generate a new `SECRET_KEY`, set the production frontend URL, and create the initial administrator credentials.
4. To enable model training and pricing predictions, configure both `GROQ_API_KEY` and `E2B_API_KEY`. Without them, the application can run but training jobs will fail.
5. Keep `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` blank unless you deliberately select one of those providers and install its dependencies.
6. Set `API_HOST` after assigning the API a public hostname. Point its DNS A record to the VM public IP before starting the stack; Caddy obtains and renews the TLS certificate automatically.

## 3. Start the backend

From `backend` on the VM:

```sh
docker compose up -d --build
docker compose ps
docker compose logs -f scheduler
```

The API is ready when `https://YOUR_API_HOST/health` returns `{ "status": "ok" }`.

## 4. Deploy the frontend

1. Push `frontend` to a Git repository.
2. In Cloudflare Pages, create a project connected to that repository.
3. Set the build command to `npm run build` and output directory to `dist`.
4. Add `VITE_API_URL=https://YOUR_API_HOST` as an environment variable.
5. Deploy and copy the resulting `pages.dev` URL into `FRONTEND_URL` and `ALLOWED_ORIGINS` in `backend/.env`.
6. Run `docker compose up -d` again to apply the updated variables.

## Operations

- Automated evaluation runs every night at 23:30 Asia/Kolkata. A Postgres advisory lock and one-active-job check prevent duplicate retraining.
- View scheduler activity with `docker compose logs -f scheduler`.
- Back up the Docker volumes before upgrades. The included free setup has no managed backup or uptime guarantee.
- Rebuild after updates with `docker compose up -d --build`.
