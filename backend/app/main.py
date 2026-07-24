"""
FastAPI entrypoint for the FinDesk server.
Mounts all route handlers from the app.routes package.
"""

# Route imports intentionally follow dotenv bootstrap because some modules load
# settings at import time.
# ruff: noqa: E402

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.agent_gateway import router as agent_gateway_router
from app.integrations.agenthub import router as agenthub_router
from app.routes.ai_costs import router as ai_costs_router
from app.routes.chat import router as chat_router
from app.routes.capabilities import router as capabilities_router
from app.routes.data_sources import router as data_sources_router
from app.routes.evals import router as evals_router
from app.routes.health import router as health_router
from app.routes.investments import router as investments_router
from app.routes.investment_research import router as investment_research_router
from app.routes.market import router as market_router
from app.routes.profile import router as profile_router
from app.routes.research import router as research_router
from app.routes.subscriptions import router as subscriptions_router
from app.routes.inbox import router as inbox_router
from app.routes.agent_runs import router as agent_runs_router
from app.routes.statement_import import router as statement_import_router
from app.routes.transactions import router as transactions_router
from app.routes.office import router as office_router
from app.routes.workspace import router as workspace_router
from app.config.settings import get_settings
from app.connectors.cache.redis_cache import close_redis_cache, redis_cache_status
from app.connectors.postgres.connection import close_pool, init_pool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    cache_status = redis_cache_status()
    logging.getLogger(__name__).info("Redis cache status: %s", cache_status)
    yield
    close_redis_cache()
    close_pool()


app = FastAPI(
    title="FinDesk Server",
    description=(
        "Personal finance analysis system with a CFO-first agent runtime. "
        "Features: expense analysis, budget coaching, audit review, "
        "and strategic finance insights."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

allowed_origins = get_settings().allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(capabilities_router)
app.include_router(data_sources_router)
app.include_router(evals_router)
app.include_router(profile_router)
app.include_router(transactions_router)
app.include_router(workspace_router)
app.include_router(office_router)
app.include_router(statement_import_router)
app.include_router(agent_runs_router)
app.include_router(agent_gateway_router)
app.include_router(agenthub_router)
app.include_router(ai_costs_router)
app.include_router(investments_router)
app.include_router(market_router)
app.include_router(investment_research_router)
app.include_router(research_router)
app.include_router(subscriptions_router)
app.include_router(inbox_router)
