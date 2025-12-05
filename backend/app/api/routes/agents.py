from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db, SyncSessionLocal
from app.schemas.agent import AgentCreate, AgentUpdate, AgentResponse, AgentRunResponse
from app.services.agent_service import AgentService
from app.services.activity_service import ActivityService
from app.models.agent import AgentStatus

router = APIRouter()


@router.get("/", response_model=List[AgentResponse])
async def get_agents(db: AsyncSession = Depends(get_db)):
    """Get all agents"""
    service = AgentService(db)
    agents = await service.get_all_agents()
    return agents


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific agent"""
    service = AgentService(db)
    agent = await service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/", response_model=AgentResponse)
async def create_agent(agent_data: AgentCreate, db: AsyncSession = Depends(get_db)):
    """Create a new agent"""
    service = AgentService(db)
    existing = await service.get_agent_by_name(agent_data.name)
    if existing:
        raise HTTPException(status_code=400, detail="Agent with this name already exists")
    agent = await service.create_agent(agent_data)
    return agent


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: int, agent_data: AgentUpdate, db: AsyncSession = Depends(get_db)):
    """Update an agent"""
    service = AgentService(db)
    agent = await service.update_agent(agent_id, agent_data)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/{agent_id}/start", response_model=AgentResponse)
async def start_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    """Start an agent"""
    service = AgentService(db)
    agent = await service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not agent.is_active:
        raise HTTPException(status_code=400, detail="Agent is disabled")

    agent = await service.update_agent_status(agent_id, AgentStatus.RUNNING)
    await service.start_agent_run(agent_id)
    return agent


@router.post("/{agent_id}/stop", response_model=AgentResponse)
async def stop_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    """Stop an agent"""
    service = AgentService(db)
    agent = await service.update_agent_status(agent_id, AgentStatus.IDLE)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/{agent_id}/pause", response_model=AgentResponse)
async def pause_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    """Pause an agent"""
    service = AgentService(db)
    agent = await service.update_agent_status(agent_id, AgentStatus.PAUSED)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("/{agent_id}/runs", response_model=List[AgentRunResponse])
async def get_agent_runs(agent_id: int, limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Get agent run history"""
    service = AgentService(db)
    runs = await service.get_agent_runs(agent_id, limit=limit)
    return runs


@router.get("/{agent_id}/activities")
async def get_agent_activities(
    agent_id: int,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """
    Get recent activities for an agent.

    Returns a list of recent agent activities showing what the agent has been doing.
    """
    # Use sync session for activity service
    sync_session = SyncSessionLocal()
    try:
        service = ActivityService(sync_session)
        activities = service.get_recent(agent_id=agent_id, limit=limit)

        return [
            {
                "id": a.id,
                "activity_type": a.activity_type.value,
                "message": a.message,
                "details": a.details,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in activities
        ]
    finally:
        sync_session.close()


@router.get("/activities/all")
async def get_all_activities(
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """
    Get recent activities for all agents.

    Returns a combined list of recent activities from all agents.
    """
    sync_session = SyncSessionLocal()
    try:
        service = ActivityService(sync_session)
        activities = service.get_recent(limit=limit)

        return [
            {
                "id": a.id,
                "agent_id": a.agent_id,
                "activity_type": a.activity_type.value,
                "message": a.message,
                "details": a.details,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in activities
        ]
    finally:
        sync_session.close()
