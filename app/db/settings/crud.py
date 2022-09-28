import logging

from app.db.models import Settings
from app.db.settings.schemas import SettingsModel
from sqlalchemy.exc import DBAPIError
from app.db.session import SessionLocal
from app.core.config import get_scheduler_obj

logger = logging.getLogger(__name__)

def validate_matching_schema(matching_schema: dict) -> bool:
    """Function that validates the matching schema

    Args:
        matching_schema (dict): Matching schema stored in the database

    Returns:
        bool: True in case is valid, False in case o invalid schema
    """
    valid_perfect_match = False
    
    if 'perfect_match' in matching_schema:
        if ('columns' in matching_schema['perfect_match']) and ('threshold' in matching_schema['perfect_match']) and ('score_to_match' in matching_schema['perfect_match']):
            valid_perfect_match = True
    
    valid_similar_match = False
    if 'similar_match' in matching_schema:
        if ('columns' in matching_schema['similar_match']) and ('threshold' in matching_schema['similar_match']) and ('score_to_match' in matching_schema['similar_match']):
            valid_similar_match = True

    valid_schema = False
    if valid_perfect_match and valid_similar_match:
        valid_schema = True
    
    return valid_schema


def retrieve_settings(id: str=None) -> dict:
    """Function that retrieves the settings

    Returns:
        dict: Settings object
    """
    try:
        with SessionLocal() as session:
            if id:
                settings = session.query(Settings).filter_by(id=id).first()
            else:
                settings = session.query(Settings).first()
    except DBAPIError as error:
        raise DBAPIError('Error on retriving settings! %s' %(error))
    return settings

def update_settings(new_settings: SettingsModel) -> dict:
    """Function updates the settings on database

    Args:
        match (SettingsModel): Match data
        status (int): Status of the match (0=processing, 1=processed, 2=error)

    Returns:
        dict: Created match 
    """
    try:
        with SessionLocal() as session:
            db_settings = session.query(Settings).filter_by(id=new_settings.id).first()
            
            #Alter Guess Who's job interval with the new value
            if db_settings.guess_who_timer != new_settings.guess_who_timer:
                scheduler = get_scheduler_obj()
                
                scheduler.reschedule_job('guess_who_task', trigger='interval', seconds=(60 * int(new_settings.guess_who_timer)))
                logger.info("Guess Who job has been scheduled to run every %s" %(int(new_settings.guess_who_timer)))

            for key, value in (new_settings.dict()).items():
                if hasattr(db_settings, key):
                    setattr(db_settings, key, value)

            session.commit()
    except DBAPIError as error:
        raise DBAPIError('Error on updating settings! %s' %(error))
    return new_settings
