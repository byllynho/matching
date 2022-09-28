from distutils.util import strtobool
from functools import lru_cache
import os
from sonador import SonadorServer
from fusionauth.fusionauth_client import FusionAuthClient
from app.api.routers.utils.websocket_connection import ConnectionManager
from apscheduler.schedulers.background import BackgroundScheduler

#Project Name that will appear on SwaggerUI
PROJECT_NAME = os.getenv("PROJECT_NAME", "visionaire-web")

#Database url
SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
if not SQLALCHEMY_DATABASE_URI:
    raise ValueError('Database environment (SQLALCHEMY_DATABASE_URI) not set!')

#Sonador credentials
SONADOR_URL = os.getenv('SONADOR_URL')
SONADOR_INTERNAL_DNS = strtobool(os.getenv('SONADOR_INTERNAL_DNS', 'False'))
SONADOR_IMAGING_SERVER = os.getenv('SONADOR_IMAGING_SERVER')
SONADOR_APITOKEN = os.getenv('SONADOR_APITOKEN')
if (not SONADOR_APITOKEN) or (not SONADOR_IMAGING_SERVER) or (not SONADOR_APITOKEN):
    raise ValueError('Missing Sonador environment credentials (SONADOR_APITOKEN, SONADOR_IMAGING_SERVER, SONADOR_APITOKEN)')

SONADOR_CONNECTION = SonadorServer(SONADOR_URL, None, None, SONADOR_APITOKEN, internal_dns=SONADOR_INTERNAL_DNS)
SONADOR_SESSION = SONADOR_CONNECTION.get_imageserver(SONADOR_IMAGING_SERVER)

#Guess who variables used for matching
TRANSFORM_PHONETIC = strtobool(os.getenv('TRANSFORM_PHONETIC', 'True'))
PHONETIC_ALGORITHM = os.getenv('PHONETIC_ALGORITHM', 'double_metaphone')
STEMMING = strtobool(os.getenv('STEMMING', 'False'))
STRING_COMPARRISON_METHOD = os.getenv('STRING_COMPARRISON_METHOD', 'damerau_levenshtein')

#Kafka configuration
KAFKA_SERVER = os.getenv('SEGAWAY_KAFKA_URL')
SEGAWAY_KAFKA_PERFECT_MATCH = os.getenv('SEGAWAY_KAFKA_PERFECT_MATCH', 'perfect_match')
if not KAFKA_SERVER:
    raise ValueError('Kakfa environment variables not set!')

#CORS - default with dev environment
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost,http://localhost:3000')
ALLOWED_ORIGINS = ALLOWED_ORIGINS.strip().split(',')

#VCM credentials
VCM_USER = os.getenv('VCM_USER')
VCM_PASSWORD = os.getenv('VCM_PASSWORD')
if (not VCM_USER) or (not VCM_PASSWORD):
    raise ValueError('VCM_USER and/or VCM_PASSWORD variables are not set!')
VCM_PROD = strtobool(os.getenv('VCM_PROD', 'False'))

#Authorization config
JWT_KEY = os.getenv('JWT_KEY')
JWT_ALGORITHMS = os.getenv("JWT_ALGORITHMS", "HS256")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE")
AUTH_URL = os.getenv("AUTH_URL")
AUTH_API_KEY = os.getenv("AUTH_API_KEY")
if (not JWT_KEY) or (not JWT_AUDIENCE):
    raise ValueError('JWT_KEY and/or JWT_AUDIENCE variables are not set!')
#  You must supply your API key and URL here
AUTH_CLIENT = FusionAuthClient(AUTH_API_KEY, AUTH_URL)
if (not AUTH_URL) or (not AUTH_API_KEY):
    raise ValueError('AUTH_URL and/or AUTH_API_KEY variables are not set!')

#Other configurations
URL_MATCH_TOOL = os.getenv("URL_MATCH_TOOL", "http://localhost:8000")
GUESS_WHO_CLEAN_TIMER = os.getenv("GUESS_WHO_CLEAN_TIMER", "30")
SEGAWAY_BROKER_URL = os.getenv("SEGAWAY_BROKER_URL", "amqp://guest:guest@message-broker:5672/")
#ON/OFF variable that helps on testing
PUBLISH_KAFKA = strtobool(os.getenv('PUBLISH_KAFKA_TEST', 'True'))
URL_WEBSOCKET = os.getenv("URL_WEBSOCKET", "ws://guess-who:8888")
PROCESSING_MATCHES_TIME_CHECK = int(os.getenv("PROCESSING_MATCHES_TIME_CHECK", "7"))

SCHEDULER = BackgroundScheduler(daemon=True)
def get_guess_who_timer():
    from app.db.settings.crud import retrieve_settings
    """Function that retrieves the timer for the Guess Who process

    Returns:
        Integer: Timer, in minutes, for for Guess Who
    """
    settings_obj = retrieve_settings()
    guess_who_timer = 60
    if settings_obj.guess_who_timer:
        guess_who_timer = settings_obj.guess_who_timer
    
    return guess_who_timer

@lru_cache()
def get_scheduler_obj() -> BackgroundScheduler:
    """Function that returns the object for the scheduler, which will be used to change the jobs intervals dynamically

    Returns:
        BackgroundScheduler: BackgroundScheduler instantiate class
    """
    global SCHEDULER
    
    return SCHEDULER

