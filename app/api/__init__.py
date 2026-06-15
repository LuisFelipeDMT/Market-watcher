from app.api.alerts_routes import router as alerts_router
from app.api.equities_routes import router as equities_router
from app.api.routes import router

__all__ = ["router", "equities_router", "alerts_router"]
