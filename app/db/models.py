from email.policy import default
from sqlalchemy import Boolean, Column, Integer, String, text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from datetime import datetime
from .session import Base

class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    first_name = Column(String)
    last_name = Column(String)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)

class SimilarMatch(Base):
    __tablename__ = "similar_match"

    id = Column(Integer, primary_key=True, index=True)
    similar_matches = Column(JSONB, nullable=False)
    orthanc_no_matches = Column(JSONB, nullable=False)
    vcm_no_matches = Column(JSONB, nullable=False)
    created_on = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

class Match(Base):
    __tablename__ = "match"

    id = Column(Integer, primary_key=True, index=True)
    match = Column(JSONB)
    status = Column(Integer,server_default='0')
    case_uid = Column(String, server_default='', nullable=False)
    study_uid = Column(String, server_default='', nullable=False)
    new_study_uid = Column(String, server_default='')
    error_reason = Column(String, server_default='')
    created_on = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    @hybrid_property
    def created_on_formatted(self):
        self.match['created_on_formatted'] = self.created_on.strftime("%m/%d/%Y-%H:%M:%S")

class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    matching_schema = Column(JSONB, nullable=False)
    email_sender = Column(String)
    smtp_server = Column(String)
    email_sender_password = Column(String)
    email_port = Column(String)
    email_internal_arrival = Column(String)
    teams_url = Column(String)
    guess_who_timer = Column(Integer,server_default='')

class GuessWho(Base):
    __tablename__ = "guess_who"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(Integer,server_default='0')
    type = Column(Integer,server_default='0')
    time = Column(Integer,server_default='0')
    number_studies = Column(Integer,server_default='0')
    number_cases = Column(Integer,server_default='0')
    study_uid = Column(String)
    number_matches = Column(Integer,server_default='0')
    message = Column(String)
    created_on = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    @hybrid_property
    def created_on_formatted(self):
        return self.created_on.strftime("%m/%d/%Y-%H:%M:%S")
    
    @hybrid_property
    def time_since(self):
        later_time = datetime.now()
        difference = later_time - self.created_on
        duration_in_s = difference.total_seconds()
        min, sec = divmod(duration_in_s, 60)
        hour, min = divmod(min, 60) 

        return "%d:%02d:%02d" % (hour, min, sec)

    
