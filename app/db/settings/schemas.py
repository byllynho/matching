from pydantic import BaseModel
from typing import List, Union, Literal, Dict, Optional
from app.db.models import Settings
 
class SettingsModel(BaseModel):
    """Schema that defines the Settings Schema"""
    id: str 
    matching_schema: dict
    email_sender: str=None
    smtp_server: str=None
    email_sender_password: str=None
    email_port: str=None
    email_internal_arrival: str=None
    teams_url: str=None
    guess_who_timer: int=None

    class Config:
        orm_mode = True