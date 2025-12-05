from fastapi import APIRouter
from .agents import router as agents_router
from .trades import router as trades_router
from .metrics import router as metrics_router
from .orchestrator import router as orchestrator_router
from .broker import router as broker_router
from .gem_hunter import router as gem_hunter_router
from .crypto import router as crypto_router

api_router = APIRouter()

api_router.include_router(agents_router, prefix="/agents", tags=["agents"])
api_router.include_router(trades_router, prefix="/trades", tags=["trades"])
api_router.include_router(metrics_router, prefix="/metrics", tags=["metrics"])
api_router.include_router(orchestrator_router, prefix="/orchestrator", tags=["orchestrator"])
api_router.include_router(broker_router, prefix="/broker", tags=["broker"])
api_router.include_router(gem_hunter_router, prefix="/gem-hunter", tags=["gem-hunter"])
api_router.include_router(crypto_router, prefix="/crypto", tags=["crypto"])
