"""
Background Scheduler for Autonomous Trading

Uses APScheduler to run trading cycles automatically based on agent configuration.
Supports both stock (gem_hunter) and crypto (crypto_hunter) agents.
"""

import structlog
from datetime import datetime
from typing import Dict, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore

from app.core.database import SyncSessionLocal
from app.models.agent import Agent, AgentStatus

logger = structlog.get_logger()

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None
_running_jobs: Dict[str, str] = {}  # agent_name -> job_id


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler instance"""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            jobstores={'default': MemoryJobStore()},
            job_defaults={
                'coalesce': True,  # Combine missed runs
                'max_instances': 1,  # Only one instance per job
                'misfire_grace_time': 60  # 1 minute grace period
            }
        )
    return _scheduler


def start_scheduler():
    """Start the scheduler if not already running"""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Background scheduler started")


def stop_scheduler():
    """Stop the scheduler"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
        _scheduler = None


async def run_crypto_hunter_cycle():
    """
    Execute a crypto hunter trading cycle.
    Called by the scheduler based on scan_interval_minutes.
    """
    from app.services.crypto_hunter.service import CryptoHunterService
    from app.services.broker.robinhood_client import RobinhoodCryptoClient

    logger.info("Scheduler triggered crypto hunter cycle", timestamp=datetime.now().isoformat())

    try:
        # Get agent config from database using sync session
        session = SyncSessionLocal()
        try:
            agent = session.query(Agent).filter(Agent.name == "crypto_hunter").first()
            if not agent:
                logger.warning("crypto_hunter agent not found in database")
                return

            if agent.status != AgentStatus.RUNNING:
                logger.info("crypto_hunter agent not in RUNNING status, skipping cycle", status=str(agent.status))
                return

            config = agent.config or {}
            if not config.get("trading_enabled", False) and not config.get("auto_trade", False):
                logger.info("Crypto trading not enabled in config, skipping cycle")
                return

            agent_id = agent.id

            # Create service with sync session (CryptoHunterService uses .query() which requires sync session)
            robinhood_client = RobinhoodCryptoClient()
            service = CryptoHunterService(
                agent_id=agent_id,
                db=session,
                robinhood_client=robinhood_client,
                config=config
            )
            result = await service.run_cycle()

            logger.info(
                "Crypto hunter cycle completed",
                screened=result.get("screened", 0),
                trades_executed=result.get("trades_executed", 0),
                positions_closed=result.get("positions_closed", 0)
            )

        finally:
            session.close()

    except Exception as e:
        logger.error("Crypto hunter cycle failed", error=str(e), exc_info=True)


async def run_gem_hunter_cycle():
    """
    Execute a gem hunter (stock) trading cycle.
    Called by the scheduler based on scan_interval_minutes.
    """
    from app.services.gem_hunter.service import GemHunterService

    logger.info("Scheduler triggered gem hunter cycle", timestamp=datetime.now().isoformat())

    try:
        session = SyncSessionLocal()
        try:
            agent = session.query(Agent).filter(Agent.name == "gem_hunter").first()
            if not agent:
                logger.warning("gem_hunter agent not found in database")
                return

            if agent.status != AgentStatus.RUNNING:
                logger.info("gem_hunter agent not in RUNNING status, skipping cycle", status=str(agent.status))
                return

            config = agent.config or {}
            if not config.get("auto_trade", False):
                logger.info("Gem hunter auto_trade not enabled, skipping cycle")
                return

        finally:
            session.close()

        service = GemHunterService()
        result = await service.run_cycle()

        logger.info(
            "Gem hunter cycle completed",
            screened=result.get("screened", 0),
            trades_executed=result.get("trades_executed", 0)
        )

    except Exception as e:
        logger.error("Gem hunter cycle failed", error=str(e), exc_info=True)


def schedule_crypto_hunter(interval_minutes: int = 15):
    """
    Schedule the crypto hunter to run at regular intervals.

    Args:
        interval_minutes: Minutes between cycles (default: 15)
    """
    global _running_jobs
    scheduler = get_scheduler()

    # Remove existing job if any
    if "crypto_hunter" in _running_jobs:
        try:
            scheduler.remove_job(_running_jobs["crypto_hunter"])
        except:
            pass

    # Add new job
    job = scheduler.add_job(
        run_crypto_hunter_cycle,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id=f"crypto_hunter_{datetime.now().timestamp()}",
        name="Crypto Hunter Trading Cycle",
        replace_existing=True
    )

    _running_jobs["crypto_hunter"] = job.id
    logger.info(f"Scheduled crypto hunter every {interval_minutes} minutes", job_id=job.id)

    return job.id


def schedule_gem_hunter(interval_minutes: int = 60):
    """
    Schedule the gem hunter to run at regular intervals.

    Args:
        interval_minutes: Minutes between cycles (default: 60)
    """
    global _running_jobs
    scheduler = get_scheduler()

    # Remove existing job if any
    if "gem_hunter" in _running_jobs:
        try:
            scheduler.remove_job(_running_jobs["gem_hunter"])
        except:
            pass

    # Add new job
    job = scheduler.add_job(
        run_gem_hunter_cycle,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id=f"gem_hunter_{datetime.now().timestamp()}",
        name="Gem Hunter Trading Cycle",
        replace_existing=True
    )

    _running_jobs["gem_hunter"] = job.id
    logger.info(f"Scheduled gem hunter every {interval_minutes} minutes", job_id=job.id)

    return job.id


def unschedule_agent(agent_name: str):
    """Remove an agent's scheduled job"""
    global _running_jobs
    scheduler = get_scheduler()

    if agent_name in _running_jobs:
        try:
            scheduler.remove_job(_running_jobs[agent_name])
            del _running_jobs[agent_name]
            logger.info(f"Unscheduled {agent_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to unschedule {agent_name}", error=str(e))
            return False
    return False


def get_scheduler_status() -> Dict:
    """Get current scheduler status and running jobs"""
    scheduler = get_scheduler()

    jobs = []
    if scheduler.running:
        for job in scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })

    return {
        "running": scheduler.running,
        "jobs": jobs,
        "active_agents": list(_running_jobs.keys())
    }


def start_agent_scheduler(agent_name: str, config: Dict) -> bool:
    """
    Start scheduled trading for an agent based on its config.

    Args:
        agent_name: Name of the agent (crypto_hunter, gem_hunter)
        config: Agent configuration dict

    Returns:
        True if successfully scheduled
    """
    interval = config.get("scan_interval_minutes", 15)

    if agent_name == "crypto_hunter":
        schedule_crypto_hunter(interval)
        return True
    elif agent_name == "gem_hunter":
        schedule_gem_hunter(interval)
        return True
    else:
        logger.warning(f"Unknown agent type for scheduling: {agent_name}")
        return False


def stop_agent_scheduler(agent_name: str) -> bool:
    """Stop scheduled trading for an agent"""
    return unschedule_agent(agent_name)
