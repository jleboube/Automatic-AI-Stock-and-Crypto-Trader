from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.core.market_hours import MarketHours, format_duration
from app.schemas.agent import RegimeResponse
from app.services.agent_service import AgentService
from app.services.orchestrator import OrchestratorService
from app.services.recommendation_service import RecommendationService
from app.models.agent import RegimeType

router = APIRouter()


class RejectRequest(BaseModel):
    reason: Optional[str] = None


@router.get("/market-hours")
async def get_market_hours():
    """
    Get comprehensive market hours status.

    Returns information about:
    - Current market session (closed, pre_market, regular, after_hours, weekend, holiday)
    - Whether stocks can be traded
    - Whether options can be traded
    - Time until market opens/closes
    - Current Eastern time
    """
    status = MarketHours.get_status()

    # Add human-readable time formatting
    if status["time_until_open"]:
        status["time_until_open_formatted"] = format_duration(status["time_until_open"])
    if status["time_until_close"]:
        status["time_until_close_formatted"] = format_duration(status["time_until_close"])

    return status


@router.get("/regime", response_model=RegimeResponse)
async def get_current_regime(db: AsyncSession = Depends(get_db)):
    """Get current market regime"""
    service = AgentService(db)
    regime = await service.get_current_regime()
    if not regime:
        raise HTTPException(status_code=404, detail="No active regime found")
    return regime


@router.post("/regime/{regime_type}")
async def set_regime(regime_type: str, qqq_price: float, recovery_strike: float = None, db: AsyncSession = Depends(get_db)):
    """Manually set market regime"""
    try:
        regime_enum = RegimeType(regime_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid regime type: {regime_type}")

    service = AgentService(db)
    regime = await service.set_regime(regime_enum, qqq_price, recovery_strike)
    return {"status": "success", "regime": regime.regime_type.value}


@router.post("/execute")
async def execute_weekly(db: AsyncSession = Depends(get_db)):
    """Manually trigger weekly execution"""
    orchestrator = OrchestratorService(db)
    result = await orchestrator.run_weekly_execution()
    return result


@router.post("/shutdown")
async def emergency_shutdown(db: AsyncSession = Depends(get_db)):
    """Emergency shutdown - stops all agents and closes positions"""
    orchestrator = OrchestratorService(db)
    result = await orchestrator.emergency_shutdown()
    return result


@router.get("/status")
async def get_orchestrator_status(db: AsyncSession = Depends(get_db)):
    """Get orchestrator status and market data"""
    service = AgentService(db)
    orchestrator = OrchestratorService(db)

    regime = await service.get_current_regime()
    market_data = await orchestrator.get_market_data()
    agents = await service.get_all_agents()
    market_hours = MarketHours.get_status()

    active_agents = [a.name for a in agents if a.status.value == "running"]

    # Get pending recommendations count
    pending_recommendations = await orchestrator.get_pending_recommendations()

    return {
        "current_regime": regime.regime_type.value if regime else None,
        "regime_started_at": regime.started_at.isoformat() if regime else None,
        "market_data": market_data,
        "market_hours": {
            "session": market_hours["session"],
            "is_open": market_hours["is_open"],
            "can_trade_stocks": market_hours["can_trade_stocks"],
            "can_trade_options": market_hours["can_trade_options"],
            "current_time_et": market_hours["current_time_et"],
            "time_until_open": format_duration(market_hours["time_until_open"]) if market_hours["time_until_open"] else None,
            "time_until_close": format_duration(market_hours["time_until_close"]) if market_hours["time_until_close"] else None,
        },
        "active_agents": active_agents,
        "total_agents": len(agents),
        "pending_recommendations": len(pending_recommendations)
    }


@router.post("/analyze")
async def analyze_only(db: AsyncSession = Depends(get_db)):
    """
    Run market analysis and generate trade recommendations WITHOUT executing.

    This endpoint analyzes current market conditions, determines the regime,
    and generates trade recommendations that are stored for user review.
    No trades are executed until explicitly approved and triggered.
    """
    orchestrator = OrchestratorService(db)
    result = await orchestrator.analyze_only()
    return result


@router.get("/recommendations")
async def get_recommendations(
    pending_only: bool = True,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """Get trade recommendations"""
    service = RecommendationService(db)

    if pending_only:
        recommendations = await service.get_pending_recommendations()
    else:
        recommendations = await service.get_all_recommendations(limit=limit)

    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "status": r.status.value,
            "regime_type": r.regime_type.value,
            "qqq_price": r.qqq_price,
            "vix": r.vix,
            "action": r.action,
            "trade_type": r.trade_type,
            "symbol": r.symbol,
            "short_strike": r.short_strike,
            "long_strike": r.long_strike,
            "expiration": r.expiration,
            "contracts": r.contracts,
            "estimated_credit": r.estimated_credit,
            "estimated_debit": r.estimated_debit,
            "max_risk": r.max_risk,
            "max_profit": r.max_profit,
            "short_delta": r.short_delta,
            "reasoning": r.reasoning,
            "risk_assessment": r.risk_assessment,
            "approved_at": r.approved_at.isoformat() if r.approved_at else None,
            "executed_at": r.executed_at.isoformat() if r.executed_at else None,
            "rejected_at": r.rejected_at.isoformat() if r.rejected_at else None,
            "rejection_reason": r.rejection_reason,
            "order_id": r.order_id,
            "execution_price": r.execution_price
        }
        for r in recommendations
    ]


@router.get("/recommendations/{recommendation_id}")
async def get_recommendation(recommendation_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific recommendation by ID"""
    service = RecommendationService(db)
    r = await service.get_recommendation_by_id(recommendation_id)

    if not r:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    return {
        "id": r.id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        "status": r.status.value,
        "regime_type": r.regime_type.value,
        "qqq_price": r.qqq_price,
        "vix": r.vix,
        "action": r.action,
        "trade_type": r.trade_type,
        "symbol": r.symbol,
        "short_strike": r.short_strike,
        "long_strike": r.long_strike,
        "expiration": r.expiration,
        "contracts": r.contracts,
        "estimated_credit": r.estimated_credit,
        "estimated_debit": r.estimated_debit,
        "max_risk": r.max_risk,
        "max_profit": r.max_profit,
        "short_delta": r.short_delta,
        "reasoning": r.reasoning,
        "risk_assessment": r.risk_assessment,
        "approved_at": r.approved_at.isoformat() if r.approved_at else None,
        "executed_at": r.executed_at.isoformat() if r.executed_at else None,
        "rejected_at": r.rejected_at.isoformat() if r.rejected_at else None,
        "rejection_reason": r.rejection_reason,
        "order_id": r.order_id,
        "execution_price": r.execution_price
    }


@router.post("/recommendations/{recommendation_id}/approve")
async def approve_recommendation(recommendation_id: int, db: AsyncSession = Depends(get_db)):
    """Approve a pending recommendation"""
    orchestrator = OrchestratorService(db)
    recommendation = await orchestrator.approve_recommendation(recommendation_id)

    if not recommendation:
        raise HTTPException(
            status_code=400,
            detail="Cannot approve: recommendation not found, already processed, or expired"
        )

    return {
        "status": "approved",
        "recommendation_id": recommendation.id,
        "message": "Recommendation approved. You can now execute it."
    }


@router.post("/recommendations/{recommendation_id}/reject")
async def reject_recommendation(
    recommendation_id: int,
    request: RejectRequest,
    db: AsyncSession = Depends(get_db)
):
    """Reject a pending recommendation"""
    orchestrator = OrchestratorService(db)
    recommendation = await orchestrator.reject_recommendation(
        recommendation_id,
        request.reason
    )

    if not recommendation:
        raise HTTPException(
            status_code=400,
            detail="Cannot reject: recommendation not found or already processed"
        )

    return {
        "status": "rejected",
        "recommendation_id": recommendation.id,
        "reason": request.reason
    }


@router.post("/recommendations/{recommendation_id}/execute")
async def execute_recommendation(recommendation_id: int, db: AsyncSession = Depends(get_db)):
    """
    Execute an approved recommendation.

    The recommendation must be in 'approved' status before it can be executed.
    This will place the actual trade order via Interactive Brokers.
    """
    orchestrator = OrchestratorService(db)
    result = await orchestrator.execute_recommendation(recommendation_id)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Execution failed")
        )

    return {
        "status": "executed",
        "recommendation_id": recommendation_id,
        "order_id": result.get("order_id"),
        "execution_price": result.get("execution_price"),
        "action": result.get("action")
    }
