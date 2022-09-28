#import native libs
import pathlib
import logging
import time
import json
from datetime import datetime

#import helpers
from visionaire.crm import CRMClient
from collections import OrderedDict

#import external libs
import pandas as pd
from pandas import DataFrame
from nltk.tokenize import word_tokenize
from phonetics import dmetaphone
from recordlinkage.preprocessing import clean, phonetic
from recordlinkage import Index, Compare

from app.db.settings.crud import retrieve_settings, validate_matching_schema

#import internal functions
from app.core.config import SONADOR_SESSION, TRANSFORM_PHONETIC, PHONETIC_ALGORITHM, STEMMING, \
    STRING_COMPARRISON_METHOD, KAFKA_SERVER, SEGAWAY_KAFKA_PERFECT_MATCH, \
    VCM_PASSWORD, VCM_PROD, VCM_USER, GUESS_WHO_CLEAN_TIMER, SONADOR_IMAGING_SERVER, SONADOR_CONNECTION

from app.api.routers.utils.env import init_kafka
from app.db.similar_match.crud import create_similar_matches
from app.db.match.schemas import CaseKafkaMatch, StudyKafkaMatch 
from app.db.match.crud import create_matches_from_kafka_obj, retrieve_list_studies_not_available_to_processing, update_arrival_match
from app.db.guess_who.crud import create_guess_who, update_guess_who, get_latest_run, query_guess_who_process, change_status

logger = logging.getLogger(__name__)

def check_before_start(check_latest: bool=False, save_log: bool=False, type: int=0, study_uid: str=None) -> dict:
    """Function that verifies if all the need pieces are working before starting the match process

    Returns:
        dict: {'ready': boolean, 'message': str}
    """
    response = {'ready': True, 'message': ''}

    #chek if we are able to connect to the imaging server
    try:
        SONADOR_SESSION = SONADOR_CONNECTION.get_imageserver(SONADOR_IMAGING_SERVER)
    except BaseException as error:
        logger.error(f'Error when trying to connect to Imaging Server! {error}')
        response = {'ready': False, 'message': 'Error connecting to imaging server! <b> Contact the development team!</b>'}

    #check if we able to connect to VCM
    try:
        crm = CRMClient(username=VCM_USER, password=VCM_PASSWORD, production=VCM_PROD)
        crm.authenticate()
    except BaseException as error:
        logger.error(f'Error when trying to connect to VCM! {error}') 
        response = {'ready': False, 'message': 'Error connecting to VCM! <b> Make sure that VCM is accessible before trying again!</b>'}

    #check if the matching schema is correct
    guess_who_settings = retrieve_settings()
    if not validate_matching_schema(guess_who_settings.matching_schema):
        logger.error('Matching Schema is not valid!')
        response = {'ready': False, 'message': 'Matching schema is not valid! <b>Please, verify that the Matching Schema is correct!</b>'}

    #check if the process is available
    if check_latest:
        guess_who_latest = get_latest_run()
        if guess_who_latest:
            if guess_who_latest.status == 0:
                response = {'ready': False, 'message': f'Process is already running!<b> Latests process has started {guess_who_latest.time_since} ago!. Give it time and try again later!</b>'}
                logger.error(f'Error! Process is already running!<b> Latests process has started {guess_who_latest.time_since} ago!. Give it time and try again later!</b>')

    #save or not a log into the table. In the future, we might need to be able to query it
    if save_log and response['ready'] == False:
        guess_who_process = create_guess_who(status=2, type=type, message=response['message'], study_uid=study_uid)

    return response

def run_process_cleaner():
    """Function that clears the Guess Who Process"""

    #get all running process that are running
    running_guess_who = query_guess_who_process(status=0)
    logger.info("Cleaning Process has started")
    if running_guess_who:
        for process in running_guess_who:
            later_time = datetime.now()
            difference = later_time - process.created_on
            duration_in_seconds = difference.total_seconds()

            #verify if the process has been running for a long time (indicating that it has failed)
            if duration_in_seconds > (int(GUESS_WHO_CLEAN_TIMER) * 60):
                logger.info("Stopping process with ID %s" % (process.id))
                change_status(process, status=2, message="Process has run for longer than " + GUESS_WHO_CLEAN_TIMER)
    logger.info("Cleaning Process has Finished")

def run_guess_who_process() -> dict:
    """Function that run the Guess Who process on demand

    Returns:
        dict: {success: boolean, message: string}
    """
    from app.tasks import guess_who_task
    response = {'success': True, 'messages': ''}
    start_retriving = time.time()
    try:

        #check if the matching process is already running
        can_run = check_before_start(True, True)
        if can_run['ready']:
            guess_who_task.delay()
        else:
            response = {'success': False, 'messages': can_run['message']}
        
    except ConnectionError as error:
        response = {'success': False, 'messages': error}
        raise ConnectionError(error)
    except BaseException as err:
        response = {'success': False, 'messages': error}
        logger.error("Erro during execution of Guess Who task: %s" % (err))
        raise BaseException(error)
    
    return response

def get_modality_summary(study) -> str:
    #create a summary of the series on the study
    xrays = 0
    mris = 0
    unknown = 0
    all_series_json = study.series_collection.json
    for serie in all_series_json:
        if serie['MainDicomTags']['Modality']:
            if serie['MainDicomTags']['Modality'] == 'MR':
                mris += 1
            elif serie['MainDicomTags']['Modality'] in ['CT', 'CR', 'XA', 'RF', 'DX']:
                xrays += 1
            else:
                unknown += 1
    return str(mris) +' MRIs / ' + str(xrays) + ' X-Rays / ' + str(unknown) + ' Others'    

def retrieve_cleaned_orthanc_dataframe(study_uid=None) -> DataFrame:
    """Retrieve and clean data from Orthanc.

    Returns:
    DataFrame: Pandas dataframe containing data from studies
    """
    
    #retrieve all series (MR and CR) on the database
    start_studies = time.time()
    query = { 'PatientName': '*' }
    if study_uid:
        query = { 'StudyInstanceUID': study_uid }
    
    all_studies = SONADOR_SESSION.query_study(query)
    
    total_studies = len(all_studies)
    
    logger.info('%s studies found!' % (total_studies))
    orthanc_to_match_dataframe = DataFrame()
    orthanc_no_uid_dataframe = DataFrame()
    logger.info(f"Time to retrieve {total_studies} studies:" + str(time.time() - start_studies))
    studies_not_to_process = retrieve_list_studies_not_available_to_processing()

    if total_studies > 0:
        #create dataframe that contains relevant data out of the series
        start_retriving = time.time()
        sonador_dataframe = pd.DataFrame(columns = ['uid', 'dob', 'patient_name', 'surgeon', 'study_description', 'institution', 'modalities'])
        for study in all_studies:
            
            #Eliminate all the studies without a case attached.
            #TODO: improve this functionality.
            if 'StudyDescription' in study.json['MainDicomTags']:
                if 'Visionaire Case' in study.json['MainDicomTags']['StudyDescription']:
                    continue
            
            #When we execute the matching on an new/updated arrival, we must run the match on instances where the match was already successful. We set the previous successful match to a different status.
            if study_uid:
                updated = update_arrival_match(study.pk)
                if updated :
                    studies_not_to_process.pop(study.pk)

            #If the study is being processed and we re-run guess-who(only on the streaming case), the processing studies should not be included on the matching.
            if study.pk in studies_not_to_process:
                continue

            modalities_summary = get_modality_summary(study)

            #add to data to dataframe (concat is 15% faster than append)
            sonador_dataframe = pd.concat([sonador_dataframe, pd.DataFrame.from_records([
                {
                    'uid': study.pk, 
                    'dob': str(study.json['PatientMainDicomTags']['PatientBirthDate']).replace("-", "") if 'PatientBirthDate' in study.json['PatientMainDicomTags'] else '',
                    'patient_name': study.json['PatientMainDicomTags']['PatientName'] if 'PatientName' in study.json['PatientMainDicomTags'] else '',
                    'surgeon': study.json['MainDicomTags']['ReferringPhysicianName'] if 'ReferringPhysicianName' in study.json['MainDicomTags'] else '',
                    'study_description': study.json['MainDicomTags']['StudyDescription'] if 'StudyDescription' in study.json['MainDicomTags'] else '',
                    'institution': study.json['MainDicomTags']['InstitutionName'] if 'InstitutionName' in study.json['MainDicomTags'] else '',
                    'total_series': len(study.series_collection.json),
                    'modalities_summary': modalities_summary
                }
                ])], ignore_index=True)
        
        if not sonador_dataframe.empty:
            logger.info(f"Time to retrieve important data from {total_studies} studies:" + str(time.time() - start_retriving))
            
            #Data Cleansing and organizing into the dataframe that will be used to match with VCM
            columns_information = {
                'patient_name': {'split': True, 'columns_created': ['patient_first_name', 'patient_middle_name', 'patient_last_name'], 'phonetic': TRANSFORM_PHONETIC, 'phonetic_algorithm': PHONETIC_ALGORITHM},
                'surgeon': {'split': True, 'columns_created': ['surgeon_first_name', 'surgeon_middle_name', 'surgeon_last_name'], 'phonetic': TRANSFORM_PHONETIC, 'phonetic_algorithm': PHONETIC_ALGORITHM},
                'institution': {'split': False, 'columns_created': ['imaging_center'], 'phonetic': False, 'phonetic_algorithm': PHONETIC_ALGORITHM, 'stemming': STEMMING}
            }

            concatenated_dataframe = pd.concat([sonador_dataframe, clear_split_names(sonador_dataframe, columns_information)], axis=1)

            #remove studies with case number on the study description
            sonador_no_case_assigned = concatenated_dataframe.loc[~concatenated_dataframe['study_description'].str.contains("Visionaire Case", case=False)]

            # Create non case number dataframe of data with uids
            # we only support Dicom 3.0 non uid cases need to handled manually (failure column??)
            with_uid, without_uid = sonador_no_case_assigned[(mask:=concatenated_dataframe['uid'] != '')], sonador_no_case_assigned[~mask]

            #These studies do not have UIDs, so there is nothing we can do to it
            orthanc_no_uid_dataframe = without_uid.filter(['uid', 'dob', 'patient_first_name', 'patient_middle_name', 'patient_last_name', 'surgeon_first_name', 'surgeon_middle_name', 'surgeon_last_name', 'imaging_center'], axis=1)

            # PRESTINE dataframe that will be used on the matching process
            orthanc_to_match_dataframe = with_uid.filter(['uid', 'dob', 'patient_name', 'patient_first_name', 'patient_middle_name', 'patient_last_name', 'surgeon', 'surgeon_first_name', 'surgeon_middle_name', 'surgeon_last_name', 'imaging_center', 'total_series', 'modalities_summary'], axis=1)
            
    return orthanc_to_match_dataframe, orthanc_no_uid_dataframe

def retrieve_cleaned_vcm_dataframe() -> DataFrame:
    """Retrieve and clean data from VCM.

    Returns:
    DataFrame: Pandas dataframe containing case data
    """

    #create authenticated session with VCM
    crm = CRMClient(username=VCM_USER, password=VCM_PASSWORD, production=VCM_PROD)
    crm.authenticate()
    
    absolute_path = pathlib.Path(__file__).parent.resolve()
    with open('app/api/routers/queries/pacs_approved_cases.xml', 'r') as f:
        pacs_cases_xml = f.read()
        
    pacs_cases = crm.fetch_xml(entity='sni_visionairecases', query=pacs_cases_xml, get_all=True)

    if pacs_cases:
        #Create dataframe that stores important data from VCM
        vcm_dataframe = pd.DataFrame([
        {
            'sni_visionairecaseid': case['sni_visionairecaseid'] if 'sni_visionairecaseid' in case else '',
            'bit_uid': case['bit_uid'] if 'bit_uid' in case else '',
            'engineer_uid': case['engineer_uid'] if 'engineer_uid' in case else '',
            'pcs_uid': case['pcs_uid'] if 'pcs_uid' in case else '',
            'primary_engineer_full_name': case['primary_engineer_full_name'] if 'primary_engineer_full_name' in case else '',
            'bit_full_name': case['bit_full_name'] if 'bit_full_name' in case else '',
            'pcs_full_name': case['pcs_full_name'] if 'pcs_full_name' in case else '',
            'dob': case['dob'] if 'dob' in case else '18000701',
            'patient_full_name': str(case['patient_last_name'] if 'patient_last_name' in case else '') + str(' ' + case['patient_first_name'] if 'patient_first_name' in case else ''), 
            'surgeon_full_name': case['surgeon_full_name'] if 'surgeon_full_name' in case else '', 
            'surgeon_last_name': case['surgeon_last_name'] if 'surgeon_last_name' in case else '',
            'surgeon_first_name': case['surgeon_first_name'] if 'surgeon_first_name' in case else '',
            'xray_center': case['xray_center'] if 'xray_center' in case else '', 
            'imaging_center': case['imaging_center'] if 'imaging_center' in case else '', 
            'case_number': case['case_number'] if 'case_number' in case else '', 
            'case_id': case['sni_visionairecaseid'] if 'sni_visionairecaseid' in case else '',
            'bilateral_case': case['bilateral_case'] if 'bilateral_case' in case else '',
            'bilateral_case_id': case['bilateral_case_id'] if 'bilateral_case_id' in case else ''
        } for case in pacs_cases])

        #Validates the DOB column to be formatted like yyyymmdd
        vcm_dataframe['dob'] = pd.to_datetime(vcm_dataframe['dob']).apply(lambda x: x.strftime('%Y%m%d')).astype(str)

        vcm_dataframe['patient_full_name'] = (vcm_dataframe['patient_full_name'].str.split().apply(lambda x: OrderedDict.fromkeys(x).keys()).str.join(' '))

        vcm_dataframe['surgeon_full_name'] = (vcm_dataframe['surgeon_full_name'].str.split().apply(lambda x: OrderedDict.fromkeys(x).keys()).str.join(' '))

        #Execute the data cleansing
        columns_information = {
            'patient_full_name': {'split': True, 'columns_created': ['patient_first_name', 'patient_middle_name', 'patient_last_name'], 'phonetic': TRANSFORM_PHONETIC, 'phonetic_algorithm': PHONETIC_ALGORITHM},
            'surgeon_first_name': {'split': False, 'columns_created': ['surgeon_first_name_updated'], 'phonetic': TRANSFORM_PHONETIC, 'phonetic_algorithm': PHONETIC_ALGORITHM},
            'surgeon_last_name': {'split': False, 'columns_created': ['surgeon_last_name_updated'], 'phonetic': TRANSFORM_PHONETIC, 'phonetic_algorithm': PHONETIC_ALGORITHM},
            'surgeon_full_name': {'split': True, 'columns_created': ['surgeon_full_first_name', 'surgeon_full_middle_name', 'surgeon_full_last_name'], 'phonetic': TRANSFORM_PHONETIC, 'phonetic_algorithm': PHONETIC_ALGORITHM},
            'imaging_center': {'split': False, 'columns_created': ['imaging_center_updated'], 'phonetic': TRANSFORM_PHONETIC, 'phonetic_algorithm': PHONETIC_ALGORITHM, 'stemming': STEMMING},
            'xray_center': {'split': False, 'columns_created': ['xray_center_updated'], 'phonetic': TRANSFORM_PHONETIC, 'phonetic_algorithm': PHONETIC_ALGORITHM, 'stemming': STEMMING}
        }

        vcm_concatenated_dataframe = pd.concat([vcm_dataframe, clear_split_names(vcm_dataframe, columns_information)], axis=1)

        #PRESTINE dataframe that will be used on the matching process
        vcm_to_match_dataframe = vcm_concatenated_dataframe.filter(['sni_visionairecaseid', 'dob', 'case_number',
            'patient_full_name', 'patient_first_name', 'patient_middle_name', 'patient_last_name', 'imaging_center', 'xray_center',
            'surgeon_full_name', 'surgeon_first_name', 'surgeon_last_name', 'surgeon_full_first_name', 'surgeon_full_middle_name', 'surgeon_full_last_name', 
            'imaging_center_updated', 'xray_center_updated', 'bit_uid', 'bit_full_name', 'pcs_uid', 'pcs_full_name', 
            'engineer_uid', 'primary_engineer_full_name', 'bilateral_case_id', 'bilateral_case'], axis=1)

        return vcm_to_match_dataframe
    
    return DataFrame()

def guess_who(guess_who_process_id: int, study_uid: str=None):
    """Retrieve and match data from Orthanc and VCM.

    Get information about studies that haven't been attached to any case and match it with cases that MIGHT be PACS
    """

    start_guess_who = time.time()

    #start kafka
    kafka_producer = init_kafka(KAFKA_SERVER)

    #get dataframes to match
    orthanc_to_match_dataframe, orthanc_no_uid_dataframe = retrieve_cleaned_orthanc_dataframe(study_uid)
    vcm_to_match_dataframe = retrieve_cleaned_vcm_dataframe()

    if orthanc_to_match_dataframe.empty:
        logger.info("No data found in Orthanc!")
        orthanc_to_match_dataframe = DataFrame()
    
    if vcm_to_match_dataframe.empty:
        logger.info("No data found in VCM!")
        vcm_to_match_dataframe = DataFrame()

    total_studies = len(vcm_to_match_dataframe)
    total_cases = len(vcm_to_match_dataframe)
    #we force all the columns to be strings. This is needed to be able to compare (sometimes other objects are created instead of string. e.g. nan, int, etc)
    orthanc_to_match_dataframe = orthanc_to_match_dataframe.astype(str)
    vcm_to_match_dataframe = vcm_to_match_dataframe.astype(str)
    
    #retrieve schema that will be used to match
    guess_who_settings = retrieve_settings()

    array_columns_to_analyze = guess_who_settings.matching_schema
    
    perfect_matches_dataframe = DataFrame()
    similar_matches_dataframe = DataFrame() 
    leftover_vcm_dataframe = DataFrame()
    leftover_orthanc_dataframe = DataFrame()
    
    #If we do not have data in one of the sides (VCM, Orthanc) we do nothing
    if (not orthanc_to_match_dataframe.empty) and (not vcm_to_match_dataframe.empty):
        perfect_matches_dataframe, similar_matches_dataframe, leftover_vcm_dataframe, leftover_orthanc_dataframe = get_matches(vcm_to_match_dataframe, orthanc_to_match_dataframe, array_columns_to_analyze)
    else:
        leftover_vcm_dataframe = vcm_to_match_dataframe
        leftover_orthanc_dataframe = orthanc_to_match_dataframe
        #filter dataframe keeping only relevant information before sending to kafka
        similar_matches_dataframe = similar_matches_dataframe.filter([
            'score', 'case_number', 'uid_vcm', 'uid_study', 'dob_study', 'dob_vcm', 'dob', 'imaging_center_vcm', 
            'xray_center_vcm', 'imaging_center_study', 'surgeon_name_vcm', 'surgeon_name_study', 'patient_name_study', 'patient_name_vcm', 
            'bit_uid', 'bit_full_name', 'pcs_uid', 'pcs_full_name', 'engineer_uid', 'primary_engineer_full_name', 'total_series', 'modalities_summary',
            'bilateral_case_id', 'bilateral_case'
        ], axis=1)
    
    #validates emptiness
    if (not perfect_matches_dataframe.empty):
        perfect_matches_dataframe = perfect_matches_dataframe.filter([
            'case_number', 'uid_vcm', 'uid_study', 'dob_study', 'dob_vcm', 'imaging_center_vcm', 'xray_center_vcm', 
            'imaging_center_study', 'surgeon_name_vcm', 'surgeon_name_study', 'patient_name_study', 'patient_name_vcm', 
            'total_series', 'modalities_summary',
        ], axis=1)

    leftover_vcm_dataframe = leftover_vcm_dataframe.filter([
        'sni_visionairecaseid', 'patient_full_name', 'surgeon_full_name', 'case_number', 
        'bit_full_name', 'pcs_full_name', 'imaging_center', 'dob'
    ], axis=1)

    leftover_orthanc_dataframe = leftover_orthanc_dataframe.filter([
        'uid', 'dob', 'patient_name', 'surgeon', 'imaging_center'
    ], axis=1)
    
    
    #Only save the similar matches if no uid is sent. Avoids generating unecessary data
    leftover_vcm_dataframe_json = {}
    similar_matches_json = {}
    leftover_orthanc_dataframe_json = {}
    if not study_uid:

        #transform similiar dataframe to json and send to database. The format created here make it easier to read on the front-end
        if not similar_matches_dataframe.empty:
            
            count_case_similiar_matches = 0
            for index, row in list(similar_matches_dataframe.iterrows()):
                match_dict = dict(row)
                if match_dict['uid_vcm'] not in similar_matches_json:
                    similar_matches_json[match_dict['uid_vcm']] = {
                            'case_number': match_dict['case_number'],
                            'uid_vcm': match_dict['uid_vcm'],
                            'imaging_center_vcm': match_dict['imaging_center_vcm'],
                            'surgeon_name_vcm': match_dict['surgeon_name_vcm'],
                            'patient_name_vcm': match_dict['patient_name_vcm'],
                            'dob_vcm': datetime.strptime(match_dict['dob_vcm'], '%Y%m%d').strftime("%m/%d/%Y") if len(match_dict['dob_vcm']) == 8 else match_dict['dob_vcm'],
                            'bit_uid': match_dict['bit_uid'],
                            'bit_full_name': match_dict['bit_full_name'],
                            'pcs_uid': match_dict['pcs_uid'],
                            'pcs_full_name': match_dict['pcs_full_name'],
                            'bilateral_case': match_dict['bilateral_case'],
                            'bilateral_case_id': match_dict['bilateral_case_id'],
                            'studies': []
                        }
                
                #keep only 3 similar cases
                if len(similar_matches_json[match_dict['uid_vcm']]['studies']) < 3:
                    similar_matches_json[match_dict['uid_vcm']]['studies'].append({
                        'imaging_center_study': match_dict['imaging_center_study'],
                        'surgeon_name_study': match_dict['surgeon_name_study'],
                        'patient_name_study': match_dict['patient_name_study'],
                        'dob_study': datetime.strptime(match_dict['dob_study'], '%Y%m%d').strftime("%m/%d/%Y") if len(match_dict['dob_study']) == 8 else match_dict['dob_study'],
                        'uid_study': match_dict['uid_study'],
                        'score': match_dict['score'],
                        'total_series': match_dict['total_series'],
                        'modalities_summary': match_dict['modalities_summary'],
                    })
                    #count_case_similiar_matches = 0
            
        #transform dataframe to a readable json to be used on the front-end
        if not leftover_orthanc_dataframe.empty:
            for index, row in list(leftover_orthanc_dataframe.iterrows()):
                leftover_orthanc_dataframe_json[row['uid']] = {
                    'uid': row['uid'], 
                    'dob': datetime.strptime(row['dob'], '%Y%m%d').strftime("%m/%d/%Y") if len(row['dob']) == 8 else row['dob'],
                    'patient_name': row['patient_name'], 
                    'surgeon': row['surgeon'], 
                    'imaging_center': row['imaging_center']
                }

        #transform dataframe to a readable json to be used on the front-end
        if not leftover_vcm_dataframe.empty:
            for index, row in list(leftover_vcm_dataframe.iterrows()):
                leftover_vcm_dataframe_json[row['sni_visionairecaseid']] = {
                    'sni_visionairecaseid': row['sni_visionairecaseid'], 
                    'patient_full_name': row['patient_full_name'], 
                    'surgeon_full_name': row['surgeon_full_name'], 
                    'case_number': row['case_number'],
                    'imaging_center_updated': row['imaging_center'],
                    'bit_full_name': row['bit_full_name'],
                    'pcs_full_name': row['pcs_full_name'],
                    'dob': datetime.strptime(row['dob'], '%Y%m%d').strftime("%m/%d/%Y") if len(row['dob']) == 8 else row['dob'],
                    }
        
        print(leftover_vcm_dataframe_json)
        #save the results of the similar matches
        create_similar_matches(similar_matches_json, leftover_orthanc_dataframe_json, leftover_vcm_dataframe_json)
              
    perfect_matches_json = {}
    
    #Start the stream of the data to the correspondent kafka topic
    if kafka_producer:
        if not perfect_matches_dataframe.empty:
            perfect_matches_json = json.loads(json.dumps(list(perfect_matches_dataframe.T.to_dict().values())))
            for match in perfect_matches_json:
                match['responsible_id'] ='Automated'
                match['responsible_name'] ='Automated'
                kafka_producer.send(SEGAWAY_KAFKA_PERFECT_MATCH, match)

            #create correct format to send to Kafka (Case has studies)
            match_data = {}
            for match in perfect_matches_json:
                if match['uid_vcm'] not in match_data:

                    match_data[match['uid_vcm']] = CaseKafkaMatch(
                        case_number=match['case_number'],
                        uid_vcm=match['uid_vcm'],
                        dob_vcm=datetime.strptime(match['dob_vcm'], '%Y%m%d').strftime("%m/%d/%Y") if len(match['dob_vcm']) == 8 else match['dob_vcm'],
                        imaging_center_vcm=match['imaging_center_vcm'],
                        xray_center_vcm=match['xray_center_vcm'],
                        surgeon_name_vcm=match['surgeon_name_vcm'],
                        patient_name_vcm=match['patient_name_vcm'],
                        responsible_name='Automated',
                        responsible_id='Automated',
                        studies=[]
                    )

                match_data[match['uid_vcm']].studies.append(StudyKafkaMatch
                    (
                        uid_study=match['uid_study'],
                        dob_study=datetime.strptime(match['dob_study'], '%Y%m%d').strftime("%m/%d/%Y") if len(match['dob_study']) == 8 else match['dob_study'],
                        imaging_center_study=match['imaging_center_study'],
                        surgeon_name_study=match['surgeon_name_study'],
                        patient_name_study=match['patient_name_study'],
                        total_series=int(float(match['total_series'])),
                        modalities_summary=match['modalities_summary'],
                    )
                ) 
            
            logger.info("Matches found: %s" % (match_data))
            send_perfect_matches(match_data)
            created_matches = create_matches_from_kafka_obj(match_data)

        kafka_producer.flush()

    return_dictionary = {'perfect': perfect_matches_json, 'similar': similar_matches_json, 'orthanc_leftover': leftover_orthanc_dataframe_json, 'vcm_leftover': leftover_vcm_dataframe_json, 'total_studies': 0, 'total_cases': 0}
    logger.info(f"Time to run the script:" + str(time.time() - start_guess_who))

    #define the type of process that will be run (0=all cases, 1=specific case)
    type_process = 0
    if study_uid:
        type_process = 1
    
    #TODO
    ## What to do with cases and series that are not similar to anything?
    ## What to do with series that do not contain UID?

    update_guess_who(guess_who_process_id, study_uid=study_uid, type=type_process, status=1, number_cases=total_cases, number_matches=int(len(perfect_matches_dataframe)), number_studies=total_studies, time=abs(int(time.time() - start_guess_who)))
    return return_dictionary

def send_perfect_matches(kafka_perfect_matches: dict):
    kafka_producer = init_kafka(KAFKA_SERVER)
    for case_uid, case_kafka_match_obj in kafka_perfect_matches.items():
        if isinstance(case_kafka_match_obj, CaseKafkaMatch):
            kafka_producer.send(SEGAWAY_KAFKA_PERFECT_MATCH, case_kafka_match_obj.dict())

def clear_split_names(dataframe: DataFrame, columns_information: list) -> DataFrame:
    """
    Function that receives a pandas dataframe and columns to be cleaned.
    """
    return_dataframe = pd.DataFrame()
    for column_used, column_information in columns_information.items():
        to_use_dataframe = pd.DataFrame()
        
        #if we need to split the column (using the ' ' delimeter) into new columns. 
        #Exemple: Full name becomes First/Last/Middle name columns
        if column_information['split']:
            to_use_dataframe[column_information['columns_created']] = pd.DataFrame(
                pd.DataFrame(
                    clean(
                        clean(
                            clean(
                                #replace the characters ^-_., with whitespaces
                                dataframe[column_used], lowercase=True, remove_brackets=True, strip_accents='unicode', replace_by_none='',replace_by_whitespace="[\\^\\-\\_\\.]"
                            #remove all non-letters from name
                            ), replace_by_none='[^ ,a-z]+'
                        #remove all word with less than 2 characters
                        ), replace_by_none=r'\b[a-z]{1,2}\b'
                    #split the string into three separated words
                    ).map(split_name).fillna("",inplace=False), 
                    columns=[column_used]
                )[column_used].to_list()
            )
        
        #Execute the same function above, but do not split the string into other columns
        else:
            to_use_dataframe[column_information['columns_created']] = pd.DataFrame(
                pd.DataFrame(
                    clean(
                        clean(
                            clean(
                                dataframe[column_used], lowercase=True, remove_brackets=True, strip_accents='unicode', replace_by_none='',replace_by_whitespace="[\\^\\_\\.]"
                            ), replace_by_none='[^ ,a-z]+'
                        ), replace_by_none=r'\b[a-z]{1,2}\b'
                    ).fillna("",inplace=False), 
                    columns=[column_used]
                )[column_used].to_list()
            )
        
        #If we want to transform the words into its phonetics representation
        if 'phonetic' in column_information:
            if column_information['phonetic']:
                phonetic_dataframe = pd.DataFrame()
                for column_created in column_information['columns_created']:
                    if column_information['phonetic_algorithm'] != 'double_metaphone':
                        phonetic_dataframe[[column_created]] = pd.DataFrame(phonetic(to_use_dataframe[column_created],column_information['phonetic_algorithm']),columns=[column_created])
                    else:
                        #if we are using the double metaphone algorithm, we apply the function 
                        #to every row on the given column. The algorith outputs a tuple containing 
                        #the found phonetics, we transform that to a string and save back to the column.
                        phonetic_dataframe[[column_created]] = pd.DataFrame(to_use_dataframe[column_created].apply(lambda x: '' if x is None else ''.join(dmetaphone(' '.join(x)))),columns=[column_created])
                to_use_dataframe = phonetic_dataframe
        
        if 'stemming' in column_information:
            if column_information['stemming']:
                stemming_dataframe = pd.DataFrame()
                for column_created in column_information['columns_created']:
                    stemming_dataframe[[column_created]] = pd.DataFrame(to_use_dataframe[column_created].apply(stem_sentence),columns=[column_created])
                to_use_dataframe = stemming_dataframe
                
        #concatenate the result of the column into the final dataframe
        return_dataframe = pd.concat([return_dataframe, to_use_dataframe], axis=1)
        
    return return_dataframe

def split_name(data_string: str) -> list:
    
    first_name:str = ''
    middle_name:str = ''
    last_name:str = ''
    # Make input a space if data is none
    if data_string is None and pd.isna(data_string):
        return (first_name,middle_name,last_name)
    
    #Split the string into three. Select the first word as the last name 
    #(DICOM convention) and the last word as the first. 
    #If there are more than 2 words, assume the rest is middle name    
    if ',' in data_string:
        array_name:str = data_string.split(',')
        first_name:str = array_name[1].strip()
        last_name:str = array_name[0].strip()
        
        if ' ' in first_name:
            new_middle_names:list = first_name.split(' ')
            first_name = new_middle_names[0].strip()
            middle_name = new_middle_names[1].strip()
            
            
        elif ' ' in last_name:
            new_middle_names:list = last_name.split(' ')
            last_name = new_middle_names[-1].strip()
            middle_name = new_middle_names[0].strip()
            

    # split name if space delimited  
    elif ' ' in data_string:

        array_name:list = data_string.split(' ')
        first_name = array_name[-1]
        last_name = array_name[0]
        middle_name = ''

        if len(array_name) >= 3:
            middle_name = array_name[1]
            if len(first_name) <= 2:
                first_name = middle_name
    
    print(first_name,middle_name,last_name)
    return (first_name,middle_name,last_name)


# NLP Processing
def stem_sentence(sentence: str) -> str:
    """
    Function that execute the stemming processing on a given field and return the final value
    """
    token_words = word_tokenize(sentence)
    # token_words
    stem_sentence = []
    for word in token_words:
        stem_sentence.append(porter.stem(word))
        stem_sentence.append(" ")
    return "".join(stem_sentence)

def compare_columns_strings(compare_object: Compare, column_tuples: list, threshold: float=0.0) -> Compare:
    """Function used to add an string match to a compare object

    Args:
      full_dataframe:
        Pandas dataframe that contains the matches and the score.
      left_dataframe:
        Pandas dataframe (VCM) that will be used as a data source
      right_dataframe:
        Pandas dataframe (Orthanc) that will be used as a data source

    Returns:
      full_dataframe with the relevant and matched information coming from the VCM and Orthanc databases
    """

    if threshold > 0.0:
        for columns in column_tuples:
            compare_object.string(columns[0],
                    columns[1],
                    method=STRING_COMPARRISON_METHOD,
                    threshold=threshold,
                    label=columns[2])
    else:
        for columns in column_tuples:
            compare_object.string(columns[0],
                    columns[1],
                    method=STRING_COMPARRISON_METHOD,
                    label=columns[2])
    
    return compare_object

def compare_columns_exact(compare_object: Compare, column_tuples: list) -> Compare:
    """Function used to add an exact match to a compare object

    Args:
      compare_object:
        Compare object.
      left_dataframe:
        Pandas dataframe (VCM) that will be used as a data source
      right_dataframe:
        Pandas dataframe (Orthance) that will be used as a data source

    Returns:
      full_dataframe with the relevant and matched information coming from the VCM and Orthanc databases
    """
    for columns in column_tuples:
        compare_object.exact(columns[0],
                columns[1],
                label=columns[2])
    
    return compare_object

def add_relevant_information(full_dataframe: DataFrame,left_dataframe: DataFrame, right_dataframe: DataFrame) -> DataFrame:
    """Function that adds relevant information to matched dataframe coming from the VCM and Orthanc dataframe.

    Receives two dataframes (left, right) and the columns that should be analyzed for matching.

    Args:
      full_dataframe:
        Pandas dataframe that contains the matches and the score.
      left_dataframe:
        Pandas dataframe (VCM) that will be used as a data source
      right_dataframe:
        Pandas dataframe (Orthance) that will be used as a data source

    Returns:
      full_dataframe with the relevant and matched information coming from the VCM and Orthanc databases
    """
    full_dataframe['case_number'] = full_dataframe['level_0'].apply(lambda x: '' if x is None else left_dataframe.at[int(x),'case_number'])
    full_dataframe['uid_vcm'] = full_dataframe['level_0'].apply(lambda x: '' if x is None else left_dataframe.at[int(x),'sni_visionairecaseid'])
    full_dataframe['patient_name_vcm'] = full_dataframe['level_0'].apply(lambda x: '' if x is None else left_dataframe.at[int(x),'patient_full_name'])
    full_dataframe['dob_vcm'] = full_dataframe['level_0'].apply(lambda x: '' if x is None else left_dataframe.at[int(x),'dob'])
    full_dataframe['imaging_center_vcm'] = full_dataframe['level_0'].apply(lambda x: '' if x is None else left_dataframe.at[int(x),'imaging_center'])
    full_dataframe['xray_center_vcm'] = full_dataframe['level_0'].apply(lambda x: '' if x is None else left_dataframe.at[int(x),'xray_center'])
    full_dataframe['surgeon_name_vcm'] = full_dataframe['level_0'].apply(lambda x: '' if x is None else left_dataframe.at[int(x),'surgeon_full_name'])
    full_dataframe['bit_uid'] = full_dataframe['level_0'].apply(lambda x: '' if x is None else left_dataframe.at[int(x),'bit_uid'])
    full_dataframe['bit_full_name'] = full_dataframe['level_0'].apply(lambda x: '' if x is None else left_dataframe.at[int(x),'bit_full_name'])
    full_dataframe['pcs_uid'] = full_dataframe['level_0'].apply(lambda x: '' if x is None else left_dataframe.at[int(x),'pcs_uid'])
    full_dataframe['pcs_full_name'] = full_dataframe['level_0'].apply(lambda x: '' if x is None else left_dataframe.at[int(x),'pcs_full_name'])
    full_dataframe['engineer_uid'] = full_dataframe['level_0'].apply(lambda x: '' if x is None else left_dataframe.at[int(x),'engineer_uid'])
    full_dataframe['bilateral_case'] = full_dataframe['level_0'].apply(lambda x: '' if x is None else left_dataframe.at[int(x),'bilateral_case'])
    full_dataframe['bilateral_case_id'] = full_dataframe['level_0'].apply(lambda x: '' if x is None else left_dataframe.at[int(x),'bilateral_case_id'])
    full_dataframe['primary_engineer_full_name'] = full_dataframe['level_0'].apply(lambda x: '' if x is None else left_dataframe.at[int(x),'primary_engineer_full_name'])

    full_dataframe['uid_study'] = full_dataframe['level_1'].apply(lambda x: '' if x is None else right_dataframe.at[int(x),'uid'])
    full_dataframe['series_uid'] = full_dataframe['level_1'].apply(lambda x: '' if x is None else right_dataframe.at[int(x),'uid'])
    full_dataframe['patient_name_study'] = full_dataframe['level_1'].apply(lambda x: '' if x is None else right_dataframe.at[int(x),'patient_name'])
    full_dataframe['surgeon_name_study'] = full_dataframe['level_1'].apply(lambda x: '' if x is None else right_dataframe.at[int(x),'surgeon'])
    full_dataframe['imaging_center_study'] = full_dataframe['level_1'].apply(lambda x: '' if x is None else right_dataframe.at[int(x),'imaging_center'])
    full_dataframe['dob_study'] = full_dataframe['level_1'].apply(lambda x: '' if x is None else right_dataframe.at[int(x),'dob'])
    full_dataframe['total_series'] = full_dataframe['level_1'].apply(lambda x: '' if x is None else right_dataframe.at[int(x),'total_series'])
    full_dataframe['modalities_summary'] = full_dataframe['level_1'].apply(lambda x: '' if x is None else right_dataframe.at[int(x),'modalities_summary'])

    return full_dataframe

def get_matches_by_importance(left_dataframe: DataFrame, right_dataframe: DataFrame, columns_to_match: list) -> DataFrame:
    """Compares two pandas dataframe using its columns as parameters.

    Receives two dataframes (left, right) and the columns that should be analyzed for matching.

    Args:
      left_dataframe:
        Pandas dataframe that the matching will occur against.
      right_dataframe:
        Pandas dataframe that will be used to match agains the left_dataframe.
      require_all_keys:
        Dictionary that contains data and information on how to execute the matching process.
        The dictionary must have a string root which is a dictionary itself.
        On the root dictionary we have other keys:
            exact: array of tuples (left_dataframe_column, right_dataframe_column, new_result_dataframe) that represent which columns must be matched 100% to be considered a perfect match
            columns: array of tuples columns (left_dataframe_column, right_dataframe_column, new_result_dataframe) that represent which columns must be matched using a given threshold to be considered a perfect match.
            score_to_match: total score of the column matching so the row will be considered a possible/exact match.
            threshold: threshold used to define what can be consider as a possible/exact match (OBS: when sent empty it generates a point based scoring)
        Sample below:
        {
            'perfect_match': {
                'exact': [
                        ('dob', 'dob', 'dob')
                ],
                'columns': [
                    ('patient_first_name','patient_first_name','patient_first_first_name'),
                ],
                'score_to_match': 2,
                'threshold': threshold_perfect_match
            },
            'similar_match': {
                'columns': [
                    ('dob', 'dob', 'dob'),
                    ('patient_first_name','patient_first_name','patient_first_first_name'),
                    ('patient_last_name','patient_last_name','patient_last_last_name'),
                ],
                'score_to_match': 0,
                'threshold': ''
            }
        }

    Returns:
      A list containing the exact matches dataframe, similiar match dataframe, non-matched data from left_dataframe and non-matched data from right_dataframe
    """
    
    #create the index using the full comparrison algorithm (try all the combinations possible)
    indexer = Index().full()
    matching_index = indexer.index(left_dataframe, right_dataframe)
    
    #set instances to compare. 
    compare_object = Compare()
    
    if columns_to_match['columns']:
        compare_object = compare_columns_strings(compare_object, columns_to_match['columns'], columns_to_match['threshold'])
    if 'exact' in columns_to_match:
        if columns_to_match['exact']:
            compare_object = compare_columns_exact(compare_object, columns_to_match['exact'])
    
    #compute the comparissons and sum the results to a score column
    features_dataframe = compare_object.compute(matching_index, left_dataframe, right_dataframe)
    
    #keep only results that score/match the parameter to be consider a match
    match_dataframe = features_dataframe[features_dataframe.sum(axis=1) >= columns_to_match['score_to_match']].reset_index()
    
    #create columns score on the datafram by summing up the results
    match_dataframe['score'] = match_dataframe.iloc[:,2:].sum(axis=1)
    
    #sort the dataframe on a descending order using the score
    match_dataframe =  match_dataframe.sort_values(by='score', ascending=False).reset_index()
    
    #add information to match dataframe
    match_dataframe = add_relevant_information(match_dataframe, left_dataframe, right_dataframe)
    
    return match_dataframe

def get_matches(left_dataframe: DataFrame, right_dataframe: DataFrame, dictionary_columns_to_match: dict) -> DataFrame:
    """Compares two pandas dataframe using its columns as parameters.

    Receives two dataframes (left, right) and the columns that should be analyzed for matching.

    Args:
      left_dataframe:
        Pandas dataframe that the matching will occur against.
      right_dataframe:
        Pandas dataframe that will be used to match agains the left_dataframe.
      require_all_keys:
        Dictionary that contains data and information on how to execute the matching process.
        The dictionary must have a string root which is a dictionary itself.
        On the root dictionary we have other keys:
            exact: array of tuples (left_dataframe_column, right_dataframe_column, new_result_dataframe) that represent which columns must be matched 100% to be considered a perfect match
            columns: array of tuples columns (left_dataframe_column, right_dataframe_column, new_result_dataframe) that represent which columns must be matched using a given threshold to be considered a perfect match.
            score_to_match: total score of the column matching so the row will be considered a possible/exact match.
            threshold: threshold used to define what can be consider as a possible/exact match (OBS: when sent empty it generates a point based scoring)
        Sample below:
        {
            'perfect_match': {
                'exact': [
                        ('dob', 'dob', 'dob')
                ],
                'columns': [
                    ('patient_first_name','patient_first_name','patient_first_first_name'),
                ],
                'score_to_match': 2,
                'threshold': threshold_perfect_match
            },
            'similar_match': {
                'columns': [
                    ('dob', 'dob', 'dob'),
                    ('patient_first_name','patient_first_name','patient_first_first_name'),
                    ('patient_last_name','patient_last_name','patient_last_last_name'),
                ],
                'score_to_match': 0,
                'threshold': ''
            }
        }

    Returns:
      A list containing the exact matches dataframe, similiar match dataframe, non-matched data from left_dataframe and non-matched data from right_dataframe
    """

    logger.info('Looking for perfect matches!')
    #get perfect matches and remove found matches from dataframe to avoid matching series/cases to more than one instance.
    perfect_matches_dataframe = get_matches_by_importance(left_dataframe, right_dataframe, dictionary_columns_to_match['perfect_match'])
    left_dataframe = left_dataframe.drop(list(set(perfect_matches_dataframe['level_0'].to_list())))
    right_dataframe = right_dataframe.drop(list(set(perfect_matches_dataframe['level_1'].to_list())))
    
    #get similiar matches and remove the found ones from the dataframes.
    similar_matches_dataframe = DataFrame()
    if dictionary_columns_to_match['similar_match']:
        logger.info('Looking for similar matches!')
        similar_matches_dataframe = get_matches_by_importance(left_dataframe, right_dataframe, dictionary_columns_to_match['similar_match'])
    
        #drop duplicated matches (a Serie can only be matched to ONE case) 
        #based on the final score (keep the one with the higher score)
        similar_matches_dataframe = similar_matches_dataframe.drop_duplicates(subset='level_1', keep="first")
        left_dataframe = left_dataframe.drop(list(set(similar_matches_dataframe['level_0'].to_list())))
        right_dataframe = right_dataframe.drop(list(set(similar_matches_dataframe['level_1'].to_list())))
    
    #return the results and the vcm cases and series not matched to anything.
    return perfect_matches_dataframe, similar_matches_dataframe, left_dataframe, right_dataframe
