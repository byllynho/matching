from pydantic import BaseModel
from typing import List, Union, Literal, Dict
from datetime import datetime

class UpdateStatusMatchModel(BaseModel):
    """Schema that defines a Match"""
    case_uid: str
    study_uid: str
    old_status: str
    new_status: str
    new_study_uid: str=None
    error_reason: str=None


class MatchModel(BaseModel):
    """Schema that defines a Match"""
    case_number: str 
    uid_vcm: str
    uid_study: str
    dob_study: str
    dob_vcm: str
    imaging_center_vcm: str
    xray_center_vcm: str
    imaging_center_study: str
    surgeon_name_vcm: str
    surgeon_name_study: str
    patient_name_study: str
    patient_name_vcm: str
    responsible_name: str
    responsible_id: str
    total_series: int
    modalities_summary: str= ''

    class Config:
        orm_mode = True
    
    @property
    def save(self, status):
        pass


class StudyKafkaMatch(BaseModel):
    """
    Schema that defines the study information on 
    the kafka topic for the perfect match
    """
    uid_study: str
    dob_study: str
    imaging_center_study: str
    surgeon_name_study: str
    patient_name_study: str
    total_series: int
    modalities_summary: str= ''

class CaseKafkaMatch(BaseModel):
    """
    Schema that defines the case information on 
    the kafka topic for the perfect match
    """
    case_number: str 
    uid_vcm: str
    dob_vcm: str
    imaging_center_vcm: str
    xray_center_vcm: str
    surgeon_name_vcm: str
    patient_name_vcm: str
    responsible_name: str
    responsible_id: str
    studies: List[StudyKafkaMatch]

    @property
    def get_matches(self):
        matches = []
        for study in self.studies:
            matches.append({
                'case_number': self.case_number,
                'uid_vcm': self.uid_vcm,
                'dob_vcm': self.dob_vcm,
                'imaging_center_vcm': self.imaging_center_vcm,
                'xray_center_vcm': self.xray_center_vcm,
                'surgeon_name_vcm': self.surgeon_name_vcm,
                'patient_name_vcm': self.patient_name_vcm,
                'responsible_name': self.responsible_name,
                'responsible_id': self.responsible_id,
                'uid_study': study.uid_study,
                'dob_study': study.dob_study,
                'imaging_center_study': study.imaging_center_study,
                'surgeon_name_study': study.surgeon_name_study,
                'patient_name_study': study.patient_name_study,
                'total_series': study.total_series,
                'modalities_summary': study.modalities_summary
                
            })

        return matches