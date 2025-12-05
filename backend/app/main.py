from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import structlog

from app.core.config import settings
from app.core.database import init_db, AsyncSessionLocal, SyncSessionLocal
from app.api.routes import api_router
from app.api.websocket import websocket_endpoint
from app.services.agent_service import AgentService
from app.schemas.agent import AgentCreate
from app.services.scheduler import (
    start_scheduler, stop_scheduler, get_scheduler,
    start_agent_scheduler, get_scheduler_status
)
from app.models.agent import Agent, AgentStatus

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()


async def seed_agents():
    """Seed the database with initial agents"""
    async with AsyncSessionLocal() as db:
        service = AgentService(db)
        agents = await service.get_all_agents()

        if not agents:
            default_agents = [
                AgentCreate(
                    name="Short-Put Agent",
                    agent_type="short_put",
                    description="Finds and executes the weekly 25-wide put credit spread",
                    config={
                        "target_credit_min": 0.55,
                        "target_credit_max": 0.70,
                        "spread_width": 25,
                        "max_delta": 0.12
                    }
                ),
                AgentCreate(
                    name="Short-Call Agent",
                    agent_type="short_call",
                    description="Runs the recovery campaign (poor-man's covered call)",
                    config={
                        "recovery_strike_offset": 0
                    }
                ),
                AgentCreate(
                    name="Long-Call Agent",
                    agent_type="long_call",
                    description="Buys the far-dated anchor calls when we flip to recovery mode",
                    config={
                        "target_expiry_months": [12, 1],
                        "strike_offset_pct": 0.03
                    }
                ),
                AgentCreate(
                    name="Long-Put Agent",
                    agent_type="long_put",
                    description="Defensive hedging only (rarely used in this strategy)",
                    config={
                        "otm_pct": 0.15,
                        "enabled": False
                    }
                ),
                AgentCreate(
                    name="Risk & Position Agent",
                    agent_type="risk",
                    description="Real-time P&L, buying-power, and max-drawdown guardian",
                    config={
                        "max_position_pct": 0.25,
                        "max_drawdown_pct": 0.15,
                        "drawdown_reduction_factor": 0.5,
                        "drawdown_reduction_weeks": 4
                    }
                ),
                AgentCreate(
                    name="Orchestrator Agent",
                    agent_type="orchestrator",
                    description="The brain - decides which regime we are in and activates agents",
                    config={
                        "execution_hour": 15,
                        "execution_minute": 45,
                        "vix_shutdown_threshold": 45.0
                    }
                ),
                AgentCreate(
                    name="gem_hunter",
                    agent_type="gem_hunter",
                    description="Autonomous agent that scans for undervalued stocks with breakout potential using technical, fundamental, and momentum analysis",
                    config={
                        "allocated_capital": 10000,
                        "max_positions": 5,
                        "max_position_pct": 0.25,
                        "kelly_multiplier": 0.5,
                        "daily_loss_limit_pct": 0.05,
                        "stop_loss_pct": 0.08,
                        "take_profit_pct": 0.20,
                        "min_composite_score": 65,
                        "max_watchlist": 20,
                        "auto_trade": True,
                        "scan_interval_minutes": 60,
                        "max_hold_days": 30,
                        "technical_weight": 0.40,
                        "fundamental_weight": 0.30,
                        "momentum_weight": 0.30,
                        "min_market_cap": 1000000000,
                        "min_avg_volume": 500000,
                        "use_limit_orders": True,
                        "limit_offset_pct": 0.001,
                        "bracket_orders": True
                    }
                ),
                AgentCreate(
                    name="crypto_hunter",
                    agent_type="crypto_hunter",
                    description="Autonomous crypto trading agent that learns trends, compares fundamentals, and executes trades via Robinhood 24/7",
                    config={
                        "allocated_capital": 5000,
                        "max_positions": 5,
                        "max_position_pct": 0.20,
                        "kelly_multiplier": 0.5,
                        "daily_loss_limit_pct": 0.05,
                        "stop_loss_pct": 0.10,
                        "take_profit_pct": 0.25,
                        "min_composite_score": 65,
                        "max_watchlist": 15,
                        "auto_trade": True,
                        "scan_interval_minutes": 30,
                        "max_hold_hours": 168,
                        "technical_weight": 0.40,
                        "fundamental_weight": 0.30,
                        "momentum_weight": 0.30,
                        "use_limit_orders": True,
                        "limit_offset_pct": 0.002,
                        "order_timeout_seconds": 120,
                        "max_slippage_pct": 0.01
                    }
                )
            ]

            for agent_data in default_agents:
                await service.create_agent(agent_data)
            logger.info("Seeded default agents")


def start_scheduled_agents():
    """Start schedulers for agents that are in RUNNING status"""
    session = SyncSessionLocal()
    try:
        # Check for running agents and start their schedulers
        running_agents = session.query(Agent).filter(
            Agent.status == AgentStatus.RUNNING
        ).all()

        for agent in running_agents:
            config = agent.config or {}
            if agent.name in ["crypto_hunter", "gem_hunter"]:
                if config.get("auto_trade", False) or config.get("trading_enabled", False):
                    start_agent_scheduler(agent.name, config)
                    logger.info(f"Started scheduler for {agent.name}")

    except Exception as e:
        logger.error("Failed to start scheduled agents", error=str(e))
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting QQQQ Agents application")
    await init_db()
    await seed_agents()

    # Start the background scheduler
    start_scheduler()
    logger.info("Background scheduler initialized")

    # Start any agents that were previously running
    start_scheduled_agents()

    yield

    # Shutdown
    logger.info("Shutting down QQQQ Agents application")
    stop_scheduler()
    logger.info("Background scheduler stopped")


app = FastAPI(
    title=settings.APP_NAME,
    description="Web application for hosting, monitoring, and managing QQQ trading agents",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api")

# WebSocket endpoint
app.add_api_websocket_route("/ws", websocket_endpoint)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    return {
        "message": "QQQQ Agents API",
        "docs": "/docs",
        "health": "/health"
    }
