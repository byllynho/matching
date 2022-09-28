from datetime import datetime
from pydantic import BaseModel

 
class GuessWhoModel(BaseModel):
    """Schema that defines the Settings Schema"""
    id: str 
    status: int=0
    type: int=0
    time: int=0
    number_studies: int=0
    number_cases: int=0
    study_uid: str=None
    number_matches: int=0
    message: str=None
    created_on: datetime= None

    class Config:
        orm_mode = True