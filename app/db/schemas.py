from pydantic import BaseModel
from typing import Dict, List, Optional

class DashboardDataModel(BaseModel):
    """Dashboard response model schema"""
    all_matches_day : int
    matched_by_user_day : int
    matched_by_user_week: int
    matched_by_user_month : int
    matches: List

    class Config:
        orm_mode = True

class ResultModel(BaseModel):
    """Basic schema for successfull execution of API"""
    
    success : bool
    messages : Optional[str]

    class Config:
        orm_mode = True



