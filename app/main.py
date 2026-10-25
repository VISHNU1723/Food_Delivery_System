
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pathlib import Path
from app.routers import auth
from app.routers import users
from app.routers import restaurants
from app.routers import menu
from app.routers import orders
from app.routers import order_items
from app.routers import payments
from app.routers import addresses
from app.routers import cart
from app.routers import coupons
from app.routers import partners
from app.routers import websockets
from contextlib import asynccontextmanager
from app.services.scheduled_jobs import start_scheduler, stop_scheduler
from app.routers import ratings
from app.routers import reports

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(
    title="Food Delivery System API",
    description="Backend API for a food delivery platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(restaurants.router)
app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(order_items.router)
app.include_router(payments.router)
app.include_router(addresses.router)
app.include_router(cart.router)
app.include_router(coupons.router)
app.include_router(partners.router)
app.include_router(websockets.router)
app.include_router(ratings.router)
app.include_router(reports.router)

@app.get("/")
def home():
    return {"message": "Food Delivery System API is running"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/tracking-test")
def tracking_test():
    html_file = Path(__file__).resolve().parent.parent / "static" / "tracking_test.html"
    return FileResponse(html_file)

@app.on_event("startup")
def startup_event():
    start_scheduler()


@app.on_event("shutdown")
def shutdown_event():
    stop_scheduler()

@app.get("/admin/scheduler-status")
def scheduler_status():
    from app.services.scheduled_jobs import scheduler

    return {
        "running": scheduler.running,
        "jobs": [
            {"id": job.id, "schedule": str(job.trigger)}
            for job in scheduler.get_jobs()
        ],
    }