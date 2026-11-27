from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.auth import bootstrap_admin, router as auth_router
from api.orders import router as orders_router
from api.predictions import router as predictions_router
from api.products import router as products_router
from api.training import recover_stale_jobs, router as training_router
from core.config import ALLOWED_ORIGINS, RUN_SCHEDULER, validate_runtime_config
from core.database import ensure_schema, get_db
from core.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_runtime_config()
    ensure_schema()
    bootstrap_admin()
    recover_stale_jobs()
    if RUN_SCHEDULER:
        start_scheduler()
    try:
        yield
    finally:
        if RUN_SCHEDULER:
            stop_scheduler()


app = FastAPI(title="PricingAI Platform", version="2.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(predictions_router, prefix="/predictions", tags=["predictions"])
app.include_router(training_router, prefix="/training", tags=["training"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(products_router, prefix="/products", tags=["products"])
app.include_router(orders_router, prefix="/orders", tags=["orders"])


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")
    return {"status": "ok", "database": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
