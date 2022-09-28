import asyncio
from typing import Union
from urllib.request import HTTPErrorProcessor
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect

import json
from datetime import datetime, date
import time
import logging

from app.db.similar_match.crud import retrieve_latest_similar_matches, retrieve_latest_similar_matches_by_bit
from app.db.match.crud import get_all_matches_db, create_match, create_matches_from_kafka_obj, get_processing_matches, \
    retrieve_processing_matches_by_case_uids, update_match_status, retrieve_matches
from app.db.settings.crud import retrieve_settings, update_settings
from app.db.match.schemas import MatchModel, CaseKafkaMatch, StudyKafkaMatch, UpdateStatusMatchModel
from app.db.schemas import DashboardDataModel, ResultModel
from app.db.settings.schemas import SettingsModel
from sse_starlette.sse import EventSourceResponse

from app.api.routers.utils.guess_who_utils import check_before_start, send_perfect_matches
from app.core.security import validate_token_url
from app.core.config import AUTH_CLIENT, PROCESSING_MATCHES_TIME_CHECK
from app.tasks import guess_who_task 
from app.db.guess_who.crud import get_latest_run, send_message_process
from app.db.guess_who.schemas import GuessWhoModel
from app.api.routers.utils.websocket_connection import ConnectionManager

logger = logging.getLogger(__name__)

guess_who_router = r = APIRouter()

@r.post('/save_match', response_model=ResultModel)
async def save_match(match: MatchModel, status: int=0, jwt_payload = Depends(validate_token_url)) -> dict:
    """Save a new match

    Args:
        match (MatchModel): Match data that will be stored in the database
        status (int): Status of the match (0=processing, 1=processed, 2=error)

    """

    try:
        create_match_response = create_match(match.json(), status)
    except BaseException as error:
        response['success'] = False
        logger.error(f'Error while saving match! {error}')
    response = {'success': True}
    
    return response

@r.put('/update_match_status', response_model=ResultModel)
async def update_status_match(match_update: UpdateStatusMatchModel, jwt_payload = Depends(validate_token_url)) -> dict:
    """Save a new match

    Args:
        match (MatchModel): Match data that will be stored in the database
        status (int): Status of the match (0=processing, 1=processed, 2=error)

    """
    response = {'success': True}
    try:
        create_match_response = update_match_status(match_update)
    except BaseException as error:
        response['success'] = False
        logger.error(f'Error while updating match! {error}')
    
    return response

@r.post('/execute_manual_matches', response_model=ResultModel)
async def execute_manual_matches(manual_matches: dict, jwt_payload = Depends(validate_token_url)) -> dict:
    """Execute the manual matching by sending data to Kafka to be processed"""
    
    response = {'success': True}
    #retrieve data about the user from auth server (name, email)
    user_response = AUTH_CLIENT.retrieve_user(jwt_payload['sub'])
    user = {}
    if user_response.was_successful():
        user = user_response.success_response
    else:
        logger.error("Error when trying to reach the auth server!")
        raise HTTPErrorProcessor("Error when trying to reach the auth server!")
        
    try:    
        #get user name. If name is not provided, we use the email
        responsible_id = jwt_payload['sub']
        responsible_name = user['user']['email']
        if ('firstName' in user['user']) and ('lastName' in user['user']):
            responsible_name = user['user']['firstName'] + ' ' + user['user']['lastName']
        elif 'firstName' in user['user']:
            responsible_name = user['user']['firstName']
        elif 'lastName' in user['user']:
            responsible_name = user['user']['lastName']

        #Get data from the text fields and send to kafka (We could retrieve data from VCM and Orthanc, however it would require several calls).
        match_data = {}
        case_uids = []
        for case_uid, match in manual_matches.items():
            case_data = match['case_text'].split(' - ')
            match_data[case_uid] = CaseKafkaMatch(
                        case_number=case_data[0][20:],
                        uid_vcm=case_uid,
                        dob_vcm=case_data[2][12:],
                        imaging_center_vcm=case_data[3][23:],
                        xray_center_vcm=case_data[3][23:],
                        surgeon_name_vcm=case_data[4][21:],
                        patient_name_vcm=case_data[1][21:],
                        responsible_name=responsible_name,
                        responsible_id=responsible_id,
                        studies=[]
                    )
            case_uids.append(case_uid)

            for study_uid, study_selected in match['study_selected'].items():
                study_data = study_selected['text'].split(' - ')

                match_data[case_uid].studies.append(StudyKafkaMatch
                    (
                        uid_study=study_uid,
                        dob_study=study_data[1][5:],
                        imaging_center_study=study_data[2][16:],
                        surgeon_name_study=study_data[3][14:],
                        patient_name_study=study_data[0][14:],
                        total_series=int(float(study_data[4][8:])),
                        modalities_summary=study_data[5][12:]
                    )
                )
        
        #we remove the cases that are being processed, so they will not be matched twice
        matches = retrieve_processing_matches_by_case_uids(case_uids)
        cases_being_processed = ''
        for match in matches:
            if match.case_uid in match_data:
                cases_being_processed += '<br> ' + match_data[match.case_uid].case_number
                
                match_data.pop(match.case_uid)

        if cases_being_processed:
            cases_being_processed = '<b>Some of the chosen cases are already being processed, check DASHBOARD: ' + cases_being_processed
            response['messages'] = {
                'type': 'warning',
                'message': cases_being_processed
            }

        #send data to kafka to be processed
        if match_data:
            send_perfect_matches(match_data)
            create_matches = create_matches_from_kafka_obj(match_data)

    except BaseException as error:
        logger.error(f'Error while saving match! {error}')
        raise error 

    return response

@r.get("/get_dashboard_data", response_model=DashboardDataModel)
async def get_dashboard_data(jwt_payload = Depends(validate_token_url)) -> dict:
    """Get All Matches on Database"""
    
    #get matches
    matches = get_all_matches_db()

    #create structure to send
    response_json = {'matched_by_user_day': 0, 'matched_by_user_week': 0, 'matched_by_user_month': 0, 'all_matches_day': 0, 'matches': matches}
    today_date = date.today()
    year_today, week_today, day_of_week_today = today_date.isocalendar()

    for match in matches:
        year_match, week_match, day_of_week_match = match.created_on.isocalendar()
        
        #only enters if the match was done this current year and month
        if (year_match == year_today) and (today_date.month == match.created_on.month):
            
            #get matches by user: month
            if isinstance(match.match, str):
                match.match = json.loads(match.match)
            if (match.match['responsible_id'] == jwt_payload['sub']):
                response_json['matched_by_user_month'] = response_json['matched_by_user_month'] + 1
            
            #get matches by user: day
            if (week_match == week_today) and (day_of_week_match == day_of_week_today) and (match.match['responsible_id'] == jwt_payload['sub']):
                response_json['matched_by_user_day'] = response_json['matched_by_user_day'] + 1
            
            #get matches by user: week
            if (week_match == week_today) and (match.match['responsible_id'] == jwt_payload['sub']):
                response_json['matched_by_user_week'] = response_json['matched_by_user_week'] + 1
            
            if (day_of_week_match == day_of_week_today):
                response_json['all_matches_day'] = response_json['all_matches_day'] + 1

        #update date format to be shown on user interface
        match.created_on_formatted
        
    return response_json

@r.get("/latest_similar_matches_by_bit")
async def latest_similar_matches_by_bit(jwt_payload = Depends(validate_token_url)) -> dict:
    """Get similiar matches from the last Guess Who run grouped by BIT Member"""

    #get data
    similar_matches_by_bit = retrieve_latest_similar_matches_by_bit()
    return similar_matches_by_bit

@r.post("/execute_arrival_matching", response_model=ResultModel)
async def execute_arrival_matching(study_instance_uid: str, send_notification: bool= True, jwt_payload = Depends(validate_token_url)) -> dict:
    """Execute the matching process on a given study"""
    
    response = {'success': True, 'message': ''}
    try:
        start_retriving = time.time()

        #create celery task
        can_run = check_before_start(save_log=True, study_uid=study_instance_uid.strip(), type=1)
        if can_run['ready']:
            guess_who_task.delay(study_instance_uid.strip(), send_notification)
        logger.info('Arrival Matching processing time: ' + str(time.time() - start_retriving))
    except ConnectionError as error:
        response = {'success': False, 'message': error}
        raise ConnectionError(error)
    except BaseException as base:
        response = {'success': False, 'messages': "Error occured during the start of the process!" + str(base)}

    return response

@r.put("/execute_case_matching", response_model=ResultModel)
async def execute_case_matching(request: Request, jwt_payload = Depends(validate_token_url)) -> dict:
    """Execute the matching process on all studies"""
    
    start_retriving = time.time()
    response = {'success': True, 'message': ''}

    #create celery task
    try:

        #check if the matching process is already running
        can_run = check_before_start(check_latest=True, save_log=True)
        if can_run['ready']:
            guess_who_task.delay()
        else:
            response = {'success': False, 'messages': can_run['message']}
        
    except ConnectionError as error:
        response = {'success': False, 'messages': error}
        raise ConnectionError(error)
    except BaseException as base:
        response = {'success': False, 'messages': "Error occured during the start of the process!" + str(base)}

    return response

@r.get("/get_settings", response_model=SettingsModel)
async def get_settings(jwt_payload = Depends(validate_token_url)) -> SettingsModel:
    """API that retrieves the settings for the Guess Who application

    Returns:
        SettingsModel: Returns a dictionary containing the settings fields
    """
    
    settings = retrieve_settings()

    return settings

@r.put("/update_settings")
async def set_settings(settings_model: SettingsModel, jwt_payload = Depends(validate_token_url)) -> SettingsModel:
    """API that updates the settings

    Args:
        settings_model (SettingsModel): Dictionary/SettingsModel schema containing the updated settings

    Returns:
        SettingsModel: Returns a dictionary containing the recently updated settings fields.
    """

    updated_settings = update_settings(settings_model)

    return updated_settings

@r.get("/get_latest_match_run")
async def get_latest_match_run(jwt_payload = Depends(validate_token_url)) -> dict:
    """Get the last guess who run and structure it to make it easier for the frontend to display"""

    #get data
    similar_match = retrieve_latest_similar_matches()

    response = {
        'similar_matches': {}, 
        'vcm_no_matches': {},
        'orthanc_no_matches': {}
        }
    
    if similar_match:
        vcm_data = []
        #loop through data and create the structure from the VCM LEFTOVER (no matched)
        if similar_match.vcm_no_matches:
            
            for uid, vcm_row in similar_match.vcm_no_matches.items():
                vcm_data.append({
                                'bit_full_name': vcm_row['bit_full_name'],
                                'case_number': vcm_row['case_number'],
                                'imaging_center_updated': vcm_row['imaging_center_updated'],
                                'patient_full_name': vcm_row['patient_full_name'],
                                'pcs_full_name': vcm_row['pcs_full_name'],
                                'surgeon_full_name': vcm_row['surgeon_full_name'],
                                'dob': vcm_row['dob'],
                            })

        #loop through data and create the structure from the ORTHANC LEFTOVER (no matched)
        orthanc_data = []
        if similar_match.orthanc_no_matches:
            for uid, orthanc_row in similar_match.orthanc_no_matches.items():
                orthanc_data.append(orthanc_row)

        response = {
            'similar_matches': similar_match.similar_matches, 
            'vcm_no_matches': vcm_data,
            'orthanc_no_matches': orthanc_data
            }

    return response

@r.get("/get_matches")
async def get_matches(limit: int = 3000, status: str=None, 
    study_uid: str=None,
    new_study_uid: str=None,
    created_from: Union[datetime, None] =None,
    created_to: Union[datetime, None] =None, 
    jwt_payload = Depends(validate_token_url)) -> dict:
    """Retrives matches registries from database

    
        limit (int, optional): Define how many rows should be brought back. Defaults to 3000.
        status (str, optional): Query by the status (0=Processing, 1=Success, 2=Error, 3=Warning, 4=Available). Defaults to None.
        study_uid (str, optional): Retrive matches attached to an study id (orthanc). Defaults to None.
        new_study_uid (str, optional): Retrive matches attached to an study generated during match(orthanc). Defaults to None.
        created_from (datetime, optional): Date of creation. Defaults to Body(default='1900-07-26T20:53:07.516Z').
        created_to (datetime, optional): "To" date of creation (blank for an specific day). Defaults to Body(default='2900-07-26T20:53:07.516Z').


        Return dict: Matches retrievied by the search
    """

    processing_matches = retrieve_matches(limit, status, study_uid, new_study_uid, created_from, created_to)

    return processing_matches

@r.get("/latest_guess_who_run", response_model=GuessWhoModel)
async def latest_guess_who_run(jwt_payload = Depends(validate_token_url)):
    """Retrieves the latest Guess Who run"""

    guess_who_latest = get_latest_run()

    return guess_who_latest


connection_manager = ConnectionManager()

@r.websocket("/check_running_process")
async def websocket_endpoint(websocket: WebSocket):
    """Websocket that allows for communication with users and server to identify the availability of the Guess Who process

    Args:
        websocket (WebSocket): Creates the WebSocket objects
    """
    
    #connects
    await connection_manager.connect(websocket)
    try:
        while True:
            
            #receive data from client
            data = await websocket.receive_text()

            #if the the data received is to start a connection with the client, we return the latest Guess Who
            if data == 'client':
                guess_who_latest = get_latest_run()
                data = send_message_process(guess_who_latest)
                await connection_manager.send_personal_message(json.dumps(data), websocket)
            else:

                #Here the message is of when the Guess Who process is executed/updated. We broadcast it to all connected clients
                await connection_manager.broadcast(data)
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)

@r.get('/processing_matches')
async def processing_matches(request: Request):
    """Server-side events endpoint that streams matches that are being processed

    Args:
        request (Request): _description_
    """

    def retrieve_processing_matches():
        processing_matches_obj = get_processing_matches()
        # Add logic here to check for new messages
        return processing_matches_obj
    async def event_generator():
        while True:
            # If client closes connection, stop sending events
            if await request.is_disconnected():
                break

            # Checks for new messages and return them to client if any

            yield {
                    "event": "processing_matches",
                    "id": "message_id",
                    "retry": 80000,
                    "data": json.dumps(retrieve_processing_matches())
            }

            await asyncio.sleep(PROCESSING_MATCHES_TIME_CHECK)

    return EventSourceResponse(event_generator())