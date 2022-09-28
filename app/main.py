from time import time
from fastapi import FastAPI
from starlette.requests import Request
import uvicorn
import logging
from app.core import config
#from app.core.celery_app import celery_app
#from app import tasks
from app.core.config import ALLOWED_ORIGINS, get_guess_who_timer, SCHEDULER, GUESS_WHO_CLEAN_TIMER
from fastapi.middleware.cors import CORSMiddleware
from app.api.routers.guess_who import guess_who_router
from app.db.guess_who.crud import get_latest_run

from app.api.routers.utils.guess_who_utils import run_guess_who_process, run_process_cleaner

logger = logging.getLogger(__name__)

app = FastAPI(title=config.PROJECT_NAME, openapi_url="/auto-match-api/openapi.json",
              docs_url="/auto-match-api/docs", redoc_url="/auto-match-api/redocs")

# Routers
app.include_router(
    guess_who_router,
    prefix="/auto-match-api",
    tags=["auto-match-api"]
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GUESS_WHO_TIMER = get_guess_who_timer()


@app.on_event("startup")
async def execute_case_matching() -> dict:
    """Function that starts the Guess Who process on the background when the application starts."""

    SCHEDULER.add_job(run_guess_who_process, trigger='interval',
                      seconds=(60 * GUESS_WHO_TIMER), id='guess_who_task')
    logger.info("Guess Who job has been scheduled to run every %s" %
                (GUESS_WHO_TIMER))

    SCHEDULER.add_job(run_process_cleaner, trigger='interval', seconds=(
        60 * int(GUESS_WHO_CLEAN_TIMER)), id='clean_guess_who_process')
    logger.info("Guess Who Cleaner has been scheduled to run every %s" %
                (GUESS_WHO_CLEAN_TIMER))

    SCHEDULER.start()
