#!/usr/bin/env python3

from app.db.session import get_db
from app.db.session import SessionLocal
from app.db.match.crud import create_match
from fastapi import Depends

def init(db=Depends(get_db)) -> None:

    #TODO: Create data for development (matches, similar_matches)
    
    pass

if __name__ == "__main__":
    print("Creating initial data")
    init()
    print("Initial data created")
