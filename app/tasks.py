from time import time
from app.core.celery_app import celery_app

import logging

#import internal functions
from app.core.config import SONADOR_SESSION, URL_MATCH_TOOL
from app.api.routers.utils.guess_who_utils import guess_who, get_modality_summary, check_before_start
from app.api.routers.utils.notifications import send_notifications
from datetime import datetime
from app.db.guess_who.crud import create_guess_who, update_guess_who

logger = logging.getLogger(__name__)

@celery_app.task
def guess_who_task(study_uid: str=None, send_notification: bool=False) -> None:
    """Celery task that executes the Guess Who job

    Args:
        study_uid (str, optional): Study Instance UID value in case the process should be ran against a single study. Defaults to None.
        send_notification (bool, optional): In case Emails should be sent (happens when matching ONE study). Defaults to False.

    Returns:
        str: _description_
    """
    type_process = 0
    if study_uid:
        type_process = 1

    start_guess_who = time()
    guess_who_process = None
    try:
        guess_who_process = create_guess_who(study_uid=study_uid, type=type_process)
        if guess_who_process:
            result = guess_who(guess_who_process_id=guess_who_process.id, study_uid=study_uid)

    except BaseException as error:
        logger.error(error)
        if guess_who_process:
            update_guess_who(guess_who_process.id, study_uid=study_uid, type=type_process, status=2, number_cases=0, number_matches=0, number_studies=0, time=abs(int(time() - start_guess_who)), message=error)
        

    #define if email should be sent
    if study_uid and send_notification:

        #define which email should be sent:
        notification_info = {}
        template = 'arrival_with_match.html'
        subject = 'Study arrived via DIRECT PUSH automatically matched'
        if result['perfect']:

            #Dictionary that contains data that will be past to the Jinja template for rendering
            notification_info = {
                "case_number": result['perfect'][0]['case_number'],
                "patient_name_vcm": result['perfect'][0]['patient_name_vcm'],
                "dob_vcm": result['perfect'][0]['dob_vcm'],
                "imaging_center_vcm": result['perfect'][0]['imaging_center_vcm'],
                "patient_name": result['perfect'][0]['patient_name_study'],
                "dob": result['perfect'][0]['dob_study'],
                "imaging_center": result['perfect'][0]['imaging_center_study'],
                "modality": result['perfect'][0]['modalities_summary'],
                "url_match_tool": URL_MATCH_TOOL
            }
        else:
            template = 'arrival_no_match.html'
            subject = 'Study arrived via DIRECT PUSH not matched'

            study_query = SONADOR_SESSION.query_study({ 'StudyInstanceUID': study_uid })

            if study_query:
                study = study_query[0]
                
                #Dictionary that contains data that will be past to the Jinja template for rendering
                notification_info = {
                    "dob": datetime.strptime(str(study.json['PatientMainDicomTags']['PatientBirthDate']), '%Y%m%d').strftime("%m/%d/%Y") if len(str(study.json['PatientMainDicomTags']['PatientBirthDate'])) == 8 else str(study.json['PatientMainDicomTags']['PatientBirthDate']),
                    "patient_name": study.json['PatientMainDicomTags']['PatientName'] if 'PatientName' in study.json['PatientMainDicomTags'] else '',
                    "imaging_center": study.json['MainDicomTags']['InstitutionName'] if 'InstitutionName' in study.json['MainDicomTags'] else '',
                    "modality": get_modality_summary(study),
                    "url_match_tool": URL_MATCH_TOOL
                }
            else:
                logger.info("Study Instance %s not found" % (study_uid))
        
        #function that is reponsible for sending the emails
        if notification_info:
            send_notifications(template, subject, **notification_info)