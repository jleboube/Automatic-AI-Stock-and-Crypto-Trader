"""
Agent Activity Service

Provides logging and querying of agent activities for visibility.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.agent import AgentActivity, AgentActivityType


class ActivityService:
    """Service for logging and querying agent activities"""

    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        agent_id: int,
        activity_type: AgentActivityType,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> AgentActivity:
        """
        Log an agent activity.

        Args:
            agent_id: ID of the agent
            activity_type: Type of activity
            message: Human-readable message
            details: Optional structured data

        Returns:
            Created AgentActivity record
        """
        activity = AgentActivity(
            agent_id=agent_id,
            activity_type=activity_type,
            message=message,
            details=details
        )
        self.db.add(activity)
        self.db.commit()
        self.db.refresh(activity)
        return activity

    def get_recent(
        self,
        agent_id: Optional[int] = None,
        limit: int = 50,
        activity_types: Optional[List[AgentActivityType]] = None,
        since: Optional[datetime] = None
    ) -> List[AgentActivity]:
        """
        Get recent agent activities.

        Args:
            agent_id: Filter by specific agent (None for all agents)
            limit: Maximum number of activities to return
            activity_types: Filter by activity types
            since: Only return activities after this time

        Returns:
            List of AgentActivity records
        """
        query = self.db.query(AgentActivity)

        if agent_id is not None:
            query = query.filter(AgentActivity.agent_id == agent_id)

        if activity_types:
            query = query.filter(AgentActivity.activity_type.in_(activity_types))

        if since:
            query = query.filter(AgentActivity.created_at >= since)

        return query.order_by(desc(AgentActivity.created_at)).limit(limit).all()

    def get_today(self, agent_id: Optional[int] = None) -> List[AgentActivity]:
        """Get today's activities for an agent or all agents"""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.get_recent(agent_id=agent_id, since=today, limit=200)

    def clear_old(self, days: int = 7) -> int:
        """
        Clear activities older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of records deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        count = self.db.query(AgentActivity).filter(
            AgentActivity.created_at < cutoff
        ).delete()
        self.db.commit()
        return count


# Convenience functions for common activity types
def log_cycle_start(db: Session, agent_id: int, details: Dict[str, Any] = None):
    """Log that an agent cycle is starting"""
    svc = ActivityService(db)
    return svc.log(
        agent_id=agent_id,
        activity_type=AgentActivityType.CYCLE_BEGIN,
        message="Agent cycle started",
        details=details
    )


def log_cycle_end(db: Session, agent_id: int, summary: Dict[str, Any]):
    """Log that an agent cycle completed"""
    svc = ActivityService(db)
    return svc.log(
        agent_id=agent_id,
        activity_type=AgentActivityType.CYCLE_END,
        message=f"Agent cycle completed",
        details=summary
    )


def log_market_closed(db: Session, agent_id: int, session: str, time_until_open: int = None):
    """Log that agent skipped due to market being closed"""
    svc = ActivityService(db)
    return svc.log(
        agent_id=agent_id,
        activity_type=AgentActivityType.MARKET_CLOSED,
        message=f"Market closed ({session}), skipping cycle",
        details={"session": session, "time_until_open": time_until_open}
    )


def log_trade_signal(db: Session, agent_id: int, symbol: str, signal_type: str, details: Dict[str, Any] = None):
    """Log a trade signal"""
    svc = ActivityService(db)
    return svc.log(
        agent_id=agent_id,
        activity_type=AgentActivityType.TRADE_SIGNAL,
        message=f"Trade signal: {signal_type} on {symbol}",
        details={"symbol": symbol, "signal_type": signal_type, **(details or {})}
    )


def log_order(db: Session, agent_id: int, order_type: str, symbol: str, details: Dict[str, Any]):
    """Log an order event"""
    svc = ActivityService(db)
    activity_map = {
        "placed": AgentActivityType.ORDER_PLACED,
        "filled": AgentActivityType.ORDER_FILLED,
        "cancelled": AgentActivityType.ORDER_CANCELLED,
    }
    return svc.log(
        agent_id=agent_id,
        activity_type=activity_map.get(order_type, AgentActivityType.INFO),
        message=f"Order {order_type}: {symbol}",
        details={"symbol": symbol, **details}
    )


def log_position(db: Session, agent_id: int, action: str, symbol: str, details: Dict[str, Any]):
    """Log a position event"""
    svc = ActivityService(db)
    activity_map = {
        "opened": AgentActivityType.POSITION_OPENED,
        "closed": AgentActivityType.POSITION_CLOSED,
        "stop_triggered": AgentActivityType.STOP_TRIGGERED,
        "target_hit": AgentActivityType.TARGET_HIT,
    }
    return svc.log(
        agent_id=agent_id,
        activity_type=activity_map.get(action, AgentActivityType.INFO),
        message=f"Position {action}: {symbol}",
        details={"symbol": symbol, **details}
    )


def log_error(db: Session, agent_id: int, error: str, details: Dict[str, Any] = None):
    """Log an error"""
    svc = ActivityService(db)
    return svc.log(
        agent_id=agent_id,
        activity_type=AgentActivityType.ERROR,
        message=f"Error: {error}",
        details=details
    )


def log_info(db: Session, agent_id: int, message: str, details: Dict[str, Any] = None):
    """Log an informational message"""
    svc = ActivityService(db)
    return svc.log(
        agent_id=agent_id,
        activity_type=AgentActivityType.INFO,
        message=message,
        details=details
    )
