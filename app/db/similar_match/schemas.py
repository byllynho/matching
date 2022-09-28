from pydantic import BaseModel
from typing import Union, Literal, Dict

class CaseSimilarMatches(BaseModel):
    """Class that specifies the schema for the similiar_match column"""
    
    case_number: str
    uid_vcm: str
    imaging_center_vcm: str
    patient_name_vcm: str
    studies: list
    dob_vcm: str= ''
    bit_uid: str= ''
    bit_full_name: str= ''
    pcs_uid: str= ''
    pcs_full_name: str= ''
    surgeon_name_vcm: str= ''

class OrthancNoMatches(BaseModel):
    """Class that specifies the schema for the orthanc_no_matches column"""
    uid: str
    dob: str = ''
    patient_name: str = ''
    imaging_center: str = ''
    surgeon: str = ''

class VcmNoMatches(BaseModel):
    """Class that specifies the schema for the vcm_no_matches column"""

    case_number: str
    surgeon_full_name: str
    patient_full_name: str
    dob: str
    bit_full_name: str
    pcs_uid: str
    pcs_full_name: str
    sni_visionairecaseid: str
    imaging_center_updated: str
    bit_uid: str = ''
    pcs_uid: str = ''
    modalities_summary: str = ''
    total_series: str = ''

class CaseSimilarMatchesModel(BaseModel):
    """Class that specifies an entry on the SimiliarMatch table"""
    
    similar_matches : Dict[str, CaseSimilarMatches] = {}
    orthanc_no_matches : Dict[str, VcmNoMatches] = {}
    vcm_no_matches : Dict[str, OrthancNoMatches] = {}

    class Config:
        orm_mode = True
