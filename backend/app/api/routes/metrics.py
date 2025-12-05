from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any

from app.core.database import get_db
from app.schemas.metrics import DashboardResponse
from app.services.metrics_service import MetricsService

router = APIRouter()


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    """Get main dashboard data"""
    service = MetricsService(db)
    data = await service.get_dashboard_data()
    return data


@router.get("/pnl-chart")
async def get_pnl_chart(days: int = 30, db: AsyncSession = Depends(get_db)):
    """Get P&L chart data"""
    service = MetricsService(db)
    data = await service.get_pnl_chart_data(days=days)
    return data


@router.get("/trades-by-type")
async def get_trades_by_type(db: AsyncSession = Depends(get_db)):
    """Get trades grouped by type"""
    service = MetricsService(db)
    data = await service.get_trade_history_by_type()
    return data


@router.get("/agent/{agent_id}")
async def get_agent_metrics(agent_id: int, hours: int = 24, db: AsyncSession = Depends(get_db)):
    """Get metrics for a specific agent"""
    service = MetricsService(db)
    metrics = await service.get_agent_metrics(agent_id, hours=hours)
    return [
        {
            "metric_name": m.metric_name,
            "metric_value": m.metric_value,
            "recorded_at": m.recorded_at.isoformat()
        }
        for m in metrics
    ]


@router.get("/system")
async def get_system_metrics(metric_name: str = None, hours: int = 24, db: AsyncSession = Depends(get_db)):
    """Get system metrics"""
    service = MetricsService(db)
    metrics = await service.get_system_metrics(metric_name=metric_name, hours=hours)
    return [
        {
            "metric_name": m.metric_name,
            "metric_value": m.metric_value,
            "metadata": m.metric_metadata,
            "recorded_at": m.recorded_at.isoformat()
        }
        for m in metrics
    ]
