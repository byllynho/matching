
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
import ssl
from datetime import datetime
from app.core.config import JWT_KEY, JWT_AUDIENCE, JWT_ALGORITHMS

reusable_oauth2 = HTTPBearer()

def validate_token_url(token: str = Depends(reusable_oauth2)) -> dict:
    """Validate JWT token sent via header and return payload"""
    
    try:
        payload = jwt.decode(
                token.credentials,
                JWT_KEY,
                algorithms=JWT_ALGORITHMS,
                audience=JWT_AUDIENCE,
            )

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=403, detail="Token expired")
    except jwt.InvalidSignatureError:
        raise HTTPException(status_code=403, detail="Invalid Token Signature")
    except jwt.InvalidAudienceError:
        raise HTTPException(status_code=403, detail="Invalid Audience")
    except jwt.DecodeError:
        raise HTTPException(status_code=403, detail="Couldn't decode the JWT token!")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Invalid JWT Token!")
    return payload


def validate_token(access_token: str) -> dict:
    """
    Validate JWT token and return payload
    """

    try:
        payload = jwt.decode(
                access_token,
                JWT_KEY,
                algorithms=JWT_ALGORITHMS,
                audience=JWT_AUDIENCE,
            )
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=403, detail="Token expired")
    except jwt.InvalidSignatureError:
        raise HTTPException(status_code=403, detail="Invalid Token Signature")
    except jwt.InvalidAudienceError:
        raise HTTPException(status_code=403, detail="Invalid Audience")
    except jwt.DecodeError:
        raise HTTPException(status_code=403, detail="Couldn't decode the JWT token!")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Invalid JWT Token!")
    
    return payload

