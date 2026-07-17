import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import time

from api.config import settings
from api.endpoints import router as api_router
from database.database import engine, Base
from monitoring.telemetry import setup_telemetry, HTTP_REQUESTS_TOTAL

# Configure Loguru logger
logger.add("aiflow_backend.log", rotation="10 MB", retention="7 days", level="INFO")

# Initialize database tables automatically
try:
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables successfully initialized.")
except Exception as e:
    logger.critical(f"Database initialization failed: {e}")

# Initialize OTel Telemetry
setup_telemetry()

# Create FastAPI app instance
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Enterprise Multi-Agent AI Workflow Orchestrator backend engine.",
    version="1.0.0"
)

# Set CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middleware to track HTTP requests and durations in Prometheus
@app.middleware("http")
async def prometheus_metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    # Extract path for mapping
    path = request.url.path
    # Exclude metrics endpoint to avoid scrape recursion count bloat
    if path != "/metrics":
        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            handler=path,
            status=str(response.status_code)
        ).inc()
        
    return response

# Attach core API routers
app.include_router(api_router)

@app.get("/")
def read_root():
    return RedirectResponse(url="/ui/")

# Mount the static frontend UI folder resolved relative to __file__
import os
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/ui", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
