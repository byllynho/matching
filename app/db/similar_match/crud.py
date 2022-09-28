from sqlalchemy.exc import DBAPIError

import typing as t
import logging
import json

from app.db.match.crud import retrieve_list_case_processing_matches
from app.db.models import SimilarMatch 
from app.db.similar_match.schemas import CaseSimilarMatchesModel
from app.db.session import SessionLocal

def create_similar_matches(similar_matches: CaseSimilarMatchesModel, orthanc_no_matches: dict=None, vcm_no_matches: dict=None) -> SimilarMatch:
    """Function that creates a new row in the similar_matches table

    Args:
        similar_matches (CaseSimilarMatchesModel): Similar matches json
        orthanc_no_matches (dict, optional): Orthanc studies that are not similar to any case. Defaults to None.
        vcm_no_matches (dict, optional): Cases that have no similiar studies. Defaults to None.

    Returns:
        SimilarMatch: Recently generated row
    """

    #validating data
    if isinstance(similar_matches, str):
            similar_matches = json.loads(similar_matches)
    
    if isinstance(orthanc_no_matches, str):
            orthanc_no_matches = json.loads(orthanc_no_matches)
    
    if isinstance(vcm_no_matches, str):
            vcm_no_matches = json.loads(vcm_no_matches)

    db_similar_matches = SimilarMatch(
        similar_matches = similar_matches,
        orthanc_no_matches = orthanc_no_matches,
        vcm_no_matches = vcm_no_matches
    )
    
    try:
        with SessionLocal() as session:
            session.add(db_similar_matches)
            session.commit()
            session.refresh(db_similar_matches)
    except DBAPIError as error:
        logging.error(f'Error on creating similar_matches! {error}')
        raise DBAPIError(f'Error on creating similar_matches! {error}')

    return db_similar_matches

def retrieve_latest_similar_matches() -> SimilarMatch:
    """Function that retrieve the latest generated similar_match

    Returns:
        SimilarMatch: Latest similar_matches
    """
    try:
        with SessionLocal() as session:
            similar_matches = session.query(SimilarMatch).order_by(SimilarMatch.created_on.desc()).first()
    except DBAPIError as error:
        logging.error(f'Error on retriving matches! {error}')
        raise DBAPIError(f'Error on retriving matches! {error}')

    return similar_matches

def retrieve_latest_similar_matches_by_bit() -> dict:
    """Function that retrieves the latest simililar_matches and create a data structure where
    the cases and its similar matches are under its responsible bit team member.

    Returns:
        dict: assigned_to: dictionary that contains cases assigned to bit members. not_assigned: cases not assigned to any bit member
    """
    #get data
    similar_matches = retrieve_latest_similar_matches()

    cases_by_bit_member = {'assigned_to': {}, 'not_assigned': []}
    if similar_matches:
    #separate into cases that have and the one that haven't been assigned to a BIT member 
        similiar_matches_json = similar_matches.similar_matches
        if isinstance(similar_matches.similar_matches, str):
            similiar_matches_json = json.loads(similar_matches.similar_matches)
        
        #retrieve case uids from dictionary and check if they are being processed. If so, they will be removed from the list
        processing_cases = retrieve_list_case_processing_matches()

        #loop through to create response schema
        for case_uid, similar_match in similiar_matches_json.items():
            if case_uid not in processing_cases:
                if similar_match['bit_full_name']:
                    if similar_match['bit_full_name'] not in cases_by_bit_member['assigned_to']:
                        cases_by_bit_member['assigned_to'][similar_match['bit_full_name']] = {
                            "name": similar_match['bit_full_name'], 
                            "uid": similar_match['bit_uid'], 
                            "cases": []}
                    cases_by_bit_member['assigned_to'][similar_match['bit_full_name']]['cases'].append(similar_match)
                else:
                    cases_by_bit_member['not_assigned'].append(similar_match)
    
    return cases_by_bit_member

def delete_successfull_study_from_similar(study_uid: str) -> dict:
    latest_similar = retrieve_latest_similar_matches()
    similiar_matches_json = latest_similar.similar_matches
    if isinstance(latest_similar.similar_matches, str):
        similiar_matches_json = json.loads(latest_similar.similar_matches)
    
    case_to_delete = ''
    for case_uid, similar_match in similiar_matches_json.items():

        to_pop_study = None
        for index, study in enumerate(similar_match['studies']):
            if study['uid_study'] == study_uid:
                to_pop_study = index

        if to_pop_study:
            similar_match['studies'].pop(to_pop_study)

        
        if not similar_match['studies']:
            case_to_delete = case_uid

    if case_to_delete:
        del similiar_matches_json[case_to_delete]
    
    
    
    update_similar_matches(similiar_matches_json=similiar_matches_json, id=latest_similar.id)

def update_similar_matches(similiar_matches_json: dict, id: str=None, similiar_match_object: SimilarMatch=None) -> dict:
    try:
        with SessionLocal() as session:
            
            db_similar_match = session.query(SimilarMatch).filter_by(id = id).first()

            db_similar_match.similar_matches = similiar_matches_json

            session.commit()

    except DBAPIError as error:
        raise DBAPIError(f'Error on updating match! {error}')
    return db_similar_match