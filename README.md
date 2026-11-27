# Pricing AI 🧠💰

An intelligent pricing and inventory optimization platform for businesses. It learns from your historical sales data, automatically selects the best-fit forecasting model, and surfaces actionable pricing and restocking recommendations — all through a clean web interface.

---

## What It Does

| Capability | Description |
|---|---|
| **AutoML Training** | Profiles your data and automatically selects & tunes the best model (Linear Regression, Ridge, Random Forest, Gradient Boosting, XGBoost) |
| **Sales Forecasting** | Predicts future demand per product using the trained model |
| **Price Optimization** | Recommends optimal prices within your defined guardrails (min/max price) |
| **Inventory Management** | Computes safety stock, reorder point, and EOQ per product |
| **Stock-Aware Pricing** | Adjusts price recommendations based on current stock levels |
| **AI Chat Agent** | Conversational assistant with access to your business data and inventory state |
| **Business Calendar** | Mark holidays / peak seasons that affect demand forecasting |
| **Auto-Retraining** | Scheduler automatically retrains when data goes stale |

---

## Architecture

```
┌─────────────────────┐        ┌──────────────────────────────────────┐
│   Vue 3 Frontend    │  HTTP  │         FastAPI Backend               │
│                     │◄──────►│                                       │
│  • Dashboard        │        │  ┌─────────┐   ┌──────────────────┐  │
│  • Products         │        │  │   API   │   │   ML Engine      │  │
│  • Orders           │        │  │ /auth   │   │                  │  │
│  • Training         │        │  │ /products│  │  profiler        │  │
│  • Predictions      │        │  │ /orders  │  │  strategist      │  │
│  • Inventory        │        │  │ /training│  │  trainer         │  │
│  • Chat             │        │  │ /predict │  │  optimizer       │  │
└─────────────────────┘        │  └────┬────┘   └───────┬──────────┘  │
                               │       │                 │             │
                               │  ┌────▼─────────────────▼──────────┐ │
                               │  │         PostgreSQL               │ │
                               │  └──────────────────────────────────┘ │
                               └──────────────────────────────────────┘
```

**ML Pipeline flow:**
```
Raw Data → Profiler → LLM Strategist → Trainer (AutoML) → Optimizer → Recommendations
```
- **Profiler** — analyses data shape, seasonality, missing values, outliers
- **LLM Strategist** — interprets the profile and writes a training plan (which features to engineer, which model families to try)
- **Trainer** — executes the plan deterministically, cross-validates, picks the best model
- **Optimizer** — runs price optimisation with inventory constraints baked in

---

## Tech Stack

**Backend**
- Python 3.11 · FastAPI · SQLAlchemy · Alembic
- scikit-learn · XGBoost · scipy (inventory math)
- Google Gemini API (LLM strategist + chat agent)
- APScheduler (background auto-retraining)
- MLflow (experiment tracking)

**Frontend**
- Vue 3 (Composition API) · Vite
- Pinia (state management)
- Chart.js

**Infrastructure**
- Docker + Docker Compose
- PostgreSQL
- GitHub Actions CI

---

## Project Structure

```
Pricing Platform/
├── backend/
│   ├── api/                  # Route handlers
│   │   ├── auth.py           # Login, register, admin user management
│   │   ├── products.py       # Product CRUD + inventory endpoints
│   │   ├── orders.py         # Order ingestion, summaries, business calendar
│   │   ├── training.py       # ML training pipeline
│   │   └── predictions.py    # Price & demand predictions
│   ├── ml/                   # ML engine
│   │   ├── profiler.py       # Data profiling
│   │   ├── strategist.py     # LLM-based training plan generator
│   │   ├── trainer.py        # AutoML training loop
│   │   └── optimizer.py      # Price + inventory optimisation
│   ├── agents/
│   │   └── chat_agent.py     # AI chat agent with business tools
│   ├── core/
│   │   ├── config.py         # App configuration
│   │   ├── database.py       # DB connection + schema bootstrap
│   │   ├── database_models.py# SQLAlchemy models
│   │   └── scheduler.py      # Auto-retraining scheduler
│   ├── models/
│   │   └── schemas.py        # Pydantic request/response schemas
│   ├── alembic/              # DB migrations
│   ├── tests/                # Unit + integration tests
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── requirements.txt
│
├── frontend/
│   └── src/
│       ├── views/            # Page components
│       ├── stores/           # Pinia stores
│       ├── components/       # Shared components
│       ├── services/api.js   # Axios API client
│       └── router/index.js
│
└── .github/workflows/ci.yml  # CI pipeline
```

---

## Getting Started (Local)

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL (or use the Docker Compose setup)

### 1. Clone the repo
```bash
git clone https://github.com/24f1001827/Pricing-AI.git
cd Pricing-AI
```

### 2. Backend setup
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -r requirements.txt

cp .env.example .env
# Fill in .env — at minimum set DATABASE_URL and GEMINI_API_KEY
```

Run migrations and start:
```bash
alembic upgrade head
uvicorn main:app --reload
```
API will be at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.

### 3. Frontend setup
```bash
cd frontend
npm install
npm run dev
```
App will be at `http://localhost:5173`.

### 4. Docker Compose (easiest)
```bash
cd backend
docker compose up --build
```
Spins up the API, scheduler, and PostgreSQL together.

---

## Configuration

Copy `backend/.env.example` to `backend/.env` and fill in:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `GEMINI_API_KEY` | Google Gemini API key (for LLM strategist + chat) |
| `SECRET_KEY` | JWT signing secret — generate with `openssl rand -hex 32` |
| `ADMIN_EMAIL` | Bootstrapped admin account email |
| `ADMIN_PASSWORD` | Bootstrapped admin account password |
| `MIN_RECORDS_TO_TRAIN` | Minimum order rows needed to trigger training (default: 50) |
| `TRAINING_STALE_MINUTES` | Auto-retrain interval in minutes (default: 1440) |

---

## Running Tests

```bash
cd backend
python -m unittest discover -s tests -v
```

---

## CI

GitHub Actions runs on every push to `main`:
- Installs Python dependencies
- Runs all backend tests
- Installs Node dependencies
- Runs ESLint + Vite build

See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---

## Key API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | Get JWT token |
| `POST` | `/auth/register` | Register new user |
| `GET` | `/products` | List products |
| `POST` | `/products` | Create product |
| `POST` | `/products/{id}/restock` | Update stock on hand |
| `GET` | `/products/{id}/apply-price` | Apply recommended price |
| `GET` | `/products/inventory-summary` | Full inventory health summary |
| `GET` | `/orders` | List orders (paginated) |
| `POST` | `/orders/upload` | Upload CSV of historical orders |
| `GET` | `/orders/summary` | Aggregated sales summary |
| `POST` | `/training/start` | Kick off a training run |
| `GET` | `/training/status` | Poll training job status |
| `GET` | `/predictions` | Get price + demand predictions |
| `POST` | `/chat` | Chat with the AI agent |
| `GET` | `/health` | Health check |

Full interactive docs available at `/docs` when the server is running.
