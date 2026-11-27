# Production Deployment Guide: Oracle Always Free + Cloudflare Pages

This setup runs the FastAPI API, PostgreSQL, MLflow, Caddy HTTPS proxy, and nightly evaluation scheduler on a single always-on VM, with the Vue frontend served globally via Cloudflare Pages.

## Architecture

| Component | Location | Notes |
| --- | --- | --- |
| Vue frontend | Cloudflare Pages | HTTPS and global static hosting |
| FastAPI API | VM (via Caddy) | Runs Alembic migrations on startup, serves `/health`, deterministic ML & inventory engine |
| Scheduler | VM | Dedicated container; runs nightly forecast evaluation & drift checks at 23:30 `SCHEDULER_TIMEZONE` |
| PostgreSQL 16 | VM | Docker volume, private network only |
| MLflow + artifacts | VM | Docker volume, private network only |

## 1. Provision the VM

1. Create an Ubuntu VM (e.g., Oracle Cloud Always Free Ampere A1, 2 OCPUs / 12 GB RAM).
2. Allow inbound TCP `22` (your IP) and TCP `80`/`443` (internet). Do **not** expose `8000`, `5432`, or `5000`.
3. Install Docker Engine and the Docker Compose plugin.
4. Clone this repository privately onto the VM.

## 2. Configure Secrets

1. Copy `backend/.env.example` to `backend/.env`.
2. Set strong random values for `POSTGRES_PASSWORD` and `SECRET_KEY` (the API fails fast at startup if `SECRET_KEY` is missing or still a placeholder).
3. Configure `INITIAL_ADMIN_EMAIL` and `INITIAL_ADMIN_PASSWORD` (at least 12 characters). Keep `ALLOW_REGISTRATION=false` and create additional team users via `POST /auth/users` as the administrator.
4. Set `API_HOST` to your API hostname and point its DNS A record to the VM IP so Caddy provisions TLS certificates automatically.
5. **Optional LLM features:** Add `GROQ_API_KEY` (or `GOOGLE_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` with matching `LLM_PROVIDER`) to enable LLM-assisted strategy explanations and conversational what-if chat. Core training, price optimization, forecasting, and inventory optimization run deterministically with no external sandbox or LLM keys required.

## 3. Start the Backend

From `backend/` on the VM:

```sh
docker compose up -d --build
docker compose ps
docker compose logs -f api scheduler
```

Verify readiness:

```sh
curl -f https://YOUR_API_HOST/health
# Expected: {"status":"ok","database":"ok"}
```

## 4. Deploy the Frontend

1. Connect the repository to Cloudflare Pages.
2. Set root directory to `frontend`, build command to `npm run build`, and output directory to `dist`.
3. Set `VITE_API_URL=https://YOUR_API_HOST`.
4. After deployment, set `FRONTEND_URL` and `ALLOWED_ORIGINS` in `backend/.env` to your `pages.dev` (or custom) URL, then run `docker compose up -d api`.

## 5. Operations & Backups

- **Database migrations:** `alembic upgrade head` runs automatically on API container startup.
- **Database backup:** Schedule a host cron to snapshot Postgres:
  ```sh
  docker compose exec -T postgres pg_dump -U pricing pricing > backup-$(date +%F).sql
  ```
- **Nightly evaluation & drift monitoring:** Runs at 23:30 `SCHEDULER_TIMEZONE` with a Postgres advisory lock (`827164`) to prevent duplicate runs.
