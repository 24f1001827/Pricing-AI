from fastapi import FastAPI
from api.predictions import router as predictions_router
from api.training import router as training_router
from api.auth import router as auth_router
from api.products import router as products_router
from api.orders import router as orders_router
from core.database import engine
from core.database_models import Base
from core.scheduler import start_scheduler, stop_scheduler
from fastapi.middleware.cors import CORSMiddleware
from core.config import ALLOWED_ORIGINS, RUN_SCHEDULER
from api.auth import bootstrap_admin

app = FastAPI(title="PricingAI Platform", version="2.0.0")

app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
Base.metadata.create_all(bind=engine)


@app.on_event("startup")
async def startup():
    bootstrap_admin()
    if RUN_SCHEDULER:
        start_scheduler()


@app.on_event("shutdown")
async def shutdown():
    if RUN_SCHEDULER:
        stop_scheduler()


app.include_router(predictions_router, prefix="/predictions", tags=["predictions"])
app.include_router(training_router, prefix="/training", tags=["training"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(products_router, prefix="/products", tags=["products"])
app.include_router(orders_router, prefix="/orders", tags=["orders"])


@app.get("/health")
def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
