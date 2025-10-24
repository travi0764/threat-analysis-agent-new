"""
Main FastAPI application for Threat Analysis Agent.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.classify import router as classify_router
from app.api.feedback import router as feedback_router
from app.api.ingest import router as ingest_router
from app.api.query import router as query_router
from app.config import get_settings
from app.enrichment.abuseipdb_enricher import AbuseIPDBEnricher
from app.enrichment.base import get_enricher_registry
from app.enrichment.malshare_enricher import MalShareEnricher
from app.enrichment.openphish_enricher import OpenPhishEnricher
from app.enrichment.phishtank_enricher import PhishTankEnricher
from app.logging_config import get_logger, setup_logging
from app.storage.db import init_database

# Load configuration
settings = get_settings()

# Setup logging
setup_logging(
    log_level=settings.logging.level,
    log_format=settings.logging.format,
    log_file=settings.logging.file,
    max_bytes=settings.logging.max_bytes,
    backup_count=settings.logging.backup_count,
)

logger = get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.app.name,
    version=settings.app.version,
    description="Intelligent agent-based system for cyber threat intelligence analysis",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
if settings.cors.enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS enabled with origins: " + ", ".join(settings.cors.origins))

# Include routers
app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(classify_router)
app.include_router(feedback_router)

# Mount static files (UI)
ui_path = Path(__file__).parent.parent / "ui"
if ui_path.exists():
    app.mount("/static", StaticFiles(directory=str(ui_path)), name="static")
    logger.info(f"Mounted UI static files from: {ui_path}")


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    logger.info(f"Starting {settings.app.name} v{settings.app.version}")

    # Initialize database
    database_url = f"sqlite:///{settings.database.path}"
    try:
        init_database(database_url, echo=settings.database.echo, recreate=False)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    # Register enrichers
    try:
        registry = get_enricher_registry()
        enrichers_registered = 0

        # Register AbuseIPDB enricher if API key is configured
        if settings.abuseipdb_api_key:
            registry.register(AbuseIPDBEnricher(settings.abuseipdb_api_key))
            logger.info("✓ AbuseIPDB enricher registered")
            enrichers_registered += 1
        else:
            logger.warning(
                "✗ AbuseIPDB API key not configured, skipping AbuseIPDB enricher"
            )

        # Register OpenPhish enricher (no API key required)
        registry.register(OpenPhishEnricher())
        logger.info("✓ OpenPhish enricher registered")
        enrichers_registered += 1

        # Register MalShare enricher if API key is configured
        if settings.malshare_api_key:
            registry.register(MalShareEnricher(settings.malshare_api_key))
            logger.info("✓ MalShare enricher registered")
            enrichers_registered += 1
        else:
            logger.warning(
                "✗ MalShare API key not configured, skipping MalShare enricher"
            )

        # Instantiate PhishTank enricher and register it if feed preloads successfully
        phishtank_enricher = PhishTankEnricher()
        try:
            feed_ok = await phishtank_enricher.ensure_feed()
        except Exception as e:
            feed_ok = False
            logger.warning("PhishTank feed preload raised exception: %s", e)

        if feed_ok:
            registry.register(phishtank_enricher)
            logger.info("✓ PhishTank enricher registered (feed loaded)")
            enrichers_registered += 1
        else:
            logger.warning(
                "✗ PhishTank feed failed to preload; skipping PhishTank enricher registration"
            )

        print(enrichers_registered)
        print("==" * 50)
        if enrichers_registered == 0:
            logger.warning(
                "⚠️  No enrichers registered! Please configure API keys in .env file. "
                "See .env.example for details."
            )

        elif enrichers_registered < 5:
            logger.info(
                f"ℹ️  {enrichers_registered}/4 enrichers registered. "
                "Configure missing API keys in .env for full functionality."
            )
    except Exception as e:
        logger.error(f"Failed to register enrichers: {e}")
        raise

    logger.info("Application startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down application")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main UI page."""
    ui_file = Path(__file__).parent.parent / "ui" / "index.html"

    if ui_file.exists():
        with open(ui_file, "r") as f:
            return HTMLResponse(content=f.read())
    else:
        return HTMLResponse(
            content="""
            <html>
                <head><title>Threat Analysis Agent</title></head>
                <body>
                    <h1>🧠 Threat Analysis Agent</h1>
                    <p>API is running!</p>
                    <ul>
                        <li><a href="/docs">API Documentation (Swagger)</a></li>
                        <li><a href="/redoc">API Documentation (ReDoc)</a></li>
                    </ul>
                </body>
            </html>
            """
        )


@app.get("/metrics.html", response_class=HTMLResponse)
async def metrics_page():
    """Serve the metrics page."""
    ui_file = Path(__file__).parent.parent / "ui" / "metrics.html"

    if ui_file.exists():
        with open(ui_file, "r") as f:
            return HTMLResponse(content=f.read())
    else:
        return HTMLResponse(
            content="<html><body><h1>Metrics page not found</h1></body></html>",
            status_code=404,
        )


@app.get("/static/{file_path:path}")
async def serve_static(file_path: str):
    """Serve static files (CSS, JS)."""
    ui_dir = Path(__file__).parent.parent / "ui"
    file = ui_dir / file_path

    if file.exists() and file.is_file():
        with open(file, "r") as f:
            content = f.read()

        # Set correct content type
        if file_path.endswith(".css"):
            return HTMLResponse(content=content, media_type="text/css")
        elif file_path.endswith(".js"):
            return HTMLResponse(content=content, media_type="application/javascript")
        else:
            return HTMLResponse(content=content)
    else:
        return HTMLResponse(content="File not found", status_code=404)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.app.version,
        "service": settings.app.name,
    }


@app.get("/api/config")
async def get_config():
    """Get public configuration (without sensitive data)."""
    return {
        "app": {
            "name": settings.app.name,
            "version": settings.app.version,
        },
        "classification": {
            "high_risk_threshold": settings.classification.high_risk_threshold,
            "medium_risk_threshold": settings.classification.medium_risk_threshold,
        },
        "scheduler": {
            "enabled": settings.scheduler.enabled,
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
        log_level=settings.logging.level.lower(),
    )
