from datetime import datetime
import logging, json, asyncio, websockets
from app.db.models import GuessWho
from sqlalchemy.exc import DBAPIError
from app.db.session import SessionLocal
from sqlalchemy import and_, event, func
from app.core.config import URL_WEBSOCKET

logger = logging.getLogger(__name__)

@event.listens_for(GuessWho, 'after_update')
def receive_after_update(mapper, connection, target):
    """Function that is triggered when there is an update to the GuessWho ORM object. It will send a message to the websocket"""
    if target.status == 1 and target.type == 0:
        asyncio.run(internal_send_message(target))

async def internal_send_message(guess_who_obj: GuessWho):
    """Function responsible for connecting to the Guess Who process websocket and send messages

    Args:
        guess_who_obj (GuessWho): _description_
    """
    async with websockets.connect(URL_WEBSOCKET + "/auto-match-api/check_running_process") as websocket:
        try:
            await websocket.send(json.dumps(send_message_process(guess_who_obj)))
            message = await websocket.recv()
        except websockets.ConnectionClosedOK as error:
            print("Disconected")
        except BaseException as err:
            logger.error("Error when trying to send messages of starting the process. %s" % (err))
            update_guess_who(guess_who_obj.id, study_uid=guess_who_obj, type=0, status=2, number_cases=0, number_matches=0, number_studies=0, time=0, message=error)

def send_message_process(guess_who_object: GuessWho):
    """Function reposible for creating the message that will be sent to the recepients 

    Args:
        guess_who_object (GuessWho): The GuessWho process object

    Returns:
        dict: {available: boolean, latest_run: string, matches: int}
    """
    message = {"available": True, "latest_run": "00:00:00", "matches": 0}
    if guess_who_object:

        message = {"available": True, "latest_run": "%s" % (guess_who_object.time_since), "matches": guess_who_object.number_matches}
        if guess_who_object.status == 0:
            message["available"] = False

    return message

def create_guess_who(status: int=0,
    type: int=0,
    time: int=0,
    number_studies: int=0,
    number_cases: int=0,
    study_uid: str=None,
    number_matches: int=0,
    message: str=None) -> dict:

    """Function that creates an entrance for the guess who process

    Returns:
        dict: Guess Who object
    """

    try:

        db_guess_who = GuessWho(
            type = type,
            status = status,
            time = time,
            number_studies = number_studies,
            number_cases = number_cases,
            study_uid = study_uid,
            number_matches = number_matches,
            message = message
        )
        
        with SessionLocal() as session:
            session.add(db_guess_who)
            session.commit()
            session.refresh(db_guess_who)
            
            #notify users of the creation of a new guess who process (make sure we are creating with status 0 == processing)
            if type == 0 and status == 0:
                asyncio.run(internal_send_message(db_guess_who))
                
    except DBAPIError as error:
        raise DBAPIError('Error on saving match! %s' % (error))
    return db_guess_who

def update_guess_who(guess_who_id: int,
    status: int=0,
    type: int=0,
    time: int=0,
    number_studies: int=0,
    number_cases: int=0,
    study_uid: str=None,
    number_matches: int=0,
    message: str=None) -> dict:

    """Function that updates the guess who process
    Args:
        match (MatchModel): Match data

    Returns:
        dict: Updated match 
    """

    try:
        with SessionLocal() as session:
            guess_who_obj = session.query(GuessWho).get(guess_who_id)
            guess_who_obj.status = status
            guess_who_obj.type = type
            guess_who_obj.time = time
            guess_who_obj.number_studies = number_studies
            guess_who_obj.number_cases = number_cases
            guess_who_obj.study_uid = study_uid
            guess_who_obj.message = message
            guess_who_obj.number_matches = number_matches

            session.commit()

    except DBAPIError as error:
        raise DBAPIError('Error on updating match! %s' % (error))

    return guess_who_obj

def update_guess_who_auto(updated_guess_who: GuessWho) -> dict:
    """Function updates the settings on database

    Args:
        match (GuessWhoModel): Match data

    Returns:
        dict: Created match 
    """
    try:
        with SessionLocal() as session:
            db_guess_who = session.query(GuessWho).get(updated_guess_who.id)
            for key, value in (updated_guess_who.dict()).items():
                if hasattr(db_guess_who, key):
                    setattr(db_guess_who, key, value)

            session.commit()
    except DBAPIError as error:
        raise DBAPIError('Error on updating settings! %s' % (error))
    return db_guess_who

def get_latest_run():
    """Function that returns the latest Guess Who process

    Returns:
        GuessWho: Guess Who object
    """
    try:
        with SessionLocal() as session:
            guess_who_obj = session.query(GuessWho).filter(GuessWho.type == 0).order_by(GuessWho.created_on.desc()).first()
    except DBAPIError as error:
        raise DBAPIError('Error on retriving latest Guess Who process! %s' % (error))

    return guess_who_obj

def query_guess_who_process(status: int=None, type: int=None, study_uid: str=None, number_matches: int=None, created_on_from: str=None, created_on_to: str=None, limit: int=5000):
    """Retrives matches based on the query attributes

    Args:
        status (int): Status of the match
        study_uid (str): Matched Study ID (Orthanc)
        new_study_uid (str): Newly generated Study ID (Orthanc)
        created_on (list): _description_

    Returns:
        Match: List of matches retrived by the search
    """
    
    with SessionLocal() as session:
        query = session.query(GuessWho)
        if status:
            query = query.filter(GuessWho.status == status)
        if study_uid:
            query = query.filter(GuessWho.study_uid == study_uid)
        if type:
            query = query.filter(GuessWho.type == type)
        if number_matches:
            query = query.filter(GuessWho.number_matches == number_matches)
        if created_on_from:
            if created_on_to:
                query = query.filter(and_(func.date(GuessWho.created_on) >= created_on_from), func.date(GuessWho.created_on) <= created_on_to)
            else:
                query = query.filter(func.date(GuessWho.created_on) == created_on_from)

        results = query.limit(limit).all()

    return results

def change_status(guess_who_obj: GuessWho, status: int, message: str=None) -> GuessWho:
    """Function that changes the status of a Guess Who Process"""
    try:
        with SessionLocal() as session:
            guess_who_obj.status = status
            if message:
                guess_who_obj.message = message

            session.commit()
    except DBAPIError as error:
        raise DBAPIError('Error on retriving latest Guess Who process! %s' % (error))

    return guess_who_obj