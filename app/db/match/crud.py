from typing import List
import logging
from app.db.models import Match
from sqlalchemy.exc import DBAPIError
from app.db.session import SessionLocal
from app.db.match.schemas import CaseKafkaMatch, MatchModel, UpdateStatusMatchModel
from sqlalchemy import inspect, or_, and_, func
import json
from sqlalchemy import update

def get_all_matches_db(limit: int=3000) -> dict:
    """Function that retrieves all matches

    Returns:
        dict: All matches in a dictionary
    """
    try:
        with SessionLocal() as session:
            matches = session.query(Match).order_by(Match.created_on.desc()).limit(limit).all()
    except DBAPIError as error:
        raise DBAPIError(f'Error on retriving matches! {error}')
    return matches

def create_match(match: dict, status=0, case_uid=None, study_uid=None, new_study_uid: str=None, error_reason: str=None) -> dict:
    """Function that creates match on database

    Args:
        match (dict): Match data
        status (int): Status of the match (0=processing, 1=processed, 2=error)

    Returns:
        dict: Created match 
    """

    try:
        if isinstance(match, str):
            match = json.loads(match)

        if not case_uid:
            case_uid = match['uid_vcm']
        if not study_uid:
            study_uid = match['uid_study']

        db_dicom_match = Match(
            match = match,
            status = status,
            case_uid = case_uid,
            study_uid = study_uid,
            new_study_uid = new_study_uid,
            error_reason = error_reason
        )
        
        with SessionLocal() as session:
            session.add(db_dicom_match)
            session.commit()
            session.refresh(db_dicom_match)
    except DBAPIError as error:
        raise DBAPIError(f'Error on saving match! {error}')
    return db_dicom_match

def update_match_status(match_update: UpdateStatusMatchModel) -> dict:
    """Function that updates the status of a match
    Args:
        match (MatchModel): Match data

    Returns:
        dict: Updated match 
    """
    from app.db.similar_match.crud import delete_successfull_study_from_similar

    try:
        with SessionLocal() as session:
            db_match = session.query(Match).filter(Match.case_uid==match_update.case_uid,Match.study_uid==match_update.study_uid,Match.status==match_update.old_status).first()
            db_match.status = match_update.new_status
            db_match.error_reason = match_update.error_reason
            db_match.new_study_uid = match_update.new_study_uid

            session.commit()
    except DBAPIError as error:
        raise DBAPIError(f'Error on updating match! {error}')

    delete_successfull_study_from_similar(match_update.study_uid)

    return db_match

def update_match(match: MatchModel) -> dict:
    """Function that creates match on database

    Args:
        match (MatchModel): Match data

    Returns:
        dict: Updated match 
    """
    try:
        with SessionLocal() as session:
            db_match = session.query(Match).filter_by(id=match.id).first()
            for key, value in (match.dict()).items():
                if hasattr(db_match, key):
                    setattr(db_match, key, value)

            session.commit()
    except DBAPIError as error:
        raise DBAPIError(f'Error on updating match! {error}')
    return match

def match_generator(session: SessionLocal, match: dict, status=0, case_uid=None, study_uid=None, new_study_uid: str=None, error_reason: str=None):
    """Function that works as a generator for new matches, adding them to the session.

    Args:
        session (SessionLocal): DB session instance
        match (dict): Data regarding a match
        status (int, optional): Status of the match. Defaults to 0.
        case_uid (_type_, optional): UID of the case on VCM. Defaults to None.
        study_uid (_type_, optional): UID of the Study in Orthanc. Defaults to None.
    """
    if isinstance(match, str):
        match = json.loads(match)

    if not case_uid:
        case_uid = match['uid_vcm']
    if not study_uid:
        study_uid = match['uid_study']

    db_dicom_match = Match(
        match = match,
        status = status,
        case_uid = case_uid,
        study_uid = study_uid,
        new_study_uid = new_study_uid,
        error_reason = error_reason
    )

    session.add(db_dicom_match)

def create_matches_from_kafka_obj(kafka_perfect_matches: dict, matches_status=0) -> dict:

    with SessionLocal() as session:
        for case_uid, case_kafka_match_obj in kafka_perfect_matches.items():
        
            if isinstance(case_kafka_match_obj, CaseKafkaMatch):
                matches_dict = case_kafka_match_obj.get_matches
                for match in matches_dict:
                    match_generator(session, match, matches_status)
        
        session.commit()

def retrieve_processing_matches_by_case_uids(case_uids: List) -> MatchModel:
    """Retrieve matches that are being processed by the uid of the case

    Args:
        case_uids (List): List of case UIDs

    Returns:
        MatchModel: List of match objects
    """
    matches = {}
    with SessionLocal() as session:
        matches = session.query(Match).filter(Match.case_uid.in_(case_uids)).filter(Match.status == 0).all()
    return matches

def retrieve_list_case_processing_matches() -> List:
    """Retrieve list of cases that are being processed

    Returns:
        List: List of case uids that are being processed
    """
    case_processing = []
    with SessionLocal() as session:
        
        case_processing = [r.case_uid for r in session.query(Match).filter(Match.status == 0).distinct()]

    return case_processing

def retrieve_list_studies_not_available_to_processing() -> List:
    """Retrieve list of cases that are being processed

    Returns:
        List: List of case uids that are being processed
    """
    study_processing = []
    study_processed_error = []
    with SessionLocal() as session:
        studies_not_to_process = [r.study_uid for r in session.query(Match).filter(or_(Match.status == 0, Match.status == 1, Match.status == 3)).distinct()]

    return studies_not_to_process

def retrieve_matches(limit: int=3000, status: int=None, study_uid: str=None, new_study_uid: str=None, created_on_from: str=None, created_on_to: str=None) -> Match:
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
        query = session.query(Match)
        if status:
            query = query.filter(Match.status == status)
        if study_uid:
            query = query.filter(Match.study_uid == study_uid)
        if new_study_uid:
            query = query.filter(Match.new_study_uid == new_study_uid)
        if created_on_from:
            if created_on_to:
                query = query.filter(and_(func.date(Match.created_on) >= created_on_from), func.date(Match.created_on) <= created_on_to)
            else:
                query = query.filter(func.date(Match.created_on) == created_on_from)
        

        results = query.limit(limit).all()

    return results

def update_arrival_match(study_uid: str) -> None:
    """Function that updates all successfull matches for a given study, so a new arrival can be matched

    Returns:
        Boolean: Returns true in case changes were made to the study
    """
    with SessionLocal() as session:
        data = session.query(Match).filter(Match.status == 1, Match.study_uid == study_uid).first()
        session.query(Match).filter(Match.status == 1, Match.study_uid == study_uid).update({Match.status: 4}, synchronize_session = False)
        session.commit()

    if data:
        return True
    
    return False
    
def object_as_dict(obj):
    """Function that converts an a list of objects to a list of dictionaries

    Args:
        obj (object): Object to convert

    Returns:
        dict: Converted
    """
    dict_return = {}
    for c in inspect(obj).mapper.column_attrs:
        if c.key == 'created_on':
            pass
        else:
            dict_return[c.key] = getattr(obj, c.key)
    return dict_return

def get_processing_matches() -> None:
    """Function that updates all successfull matches for a given study, so a new arrival can be matched

    Returns:
        Boolean: Returns true in case changes were made to the study
    """
    with SessionLocal() as session:
        processing_match = [object_as_dict(u) for u in session.query(Match).filter(Match.status == 0).all()]
    
    return processing_match