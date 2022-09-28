from celery import Celery
from app.core.config import SEGAWAY_BROKER_URL

celery_app = Celery("tasks", broker=SEGAWAY_BROKER_URL)
