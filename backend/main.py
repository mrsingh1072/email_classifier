from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, List
import os
import hashlib
from dotenv import load_dotenv
from bson import ObjectId

load_dotenv()

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Initialize FastAPI
app = FastAPI(title="Email Classifier API (Mock)", version="1.0.0")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage (mock database)
users_db: Dict[str, dict] = {}
emails_db: Dict[str, list] = {}
notifications_db: Dict[str, list] = {}

# OAuth2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")

# Pydantic Models
class UserSignup(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict

class IMAPConfig(BaseModel):
    email: EmailStr
    password: str

class EmailResponse(BaseModel):
    id: str
    subject: str
    from_: str
    date: datetime
    body: str
    category: str
    confidence: float

# Utility Functions
def verify_password(plain_password, hashed_password):
    """Verify a password against its hash using SHA256"""
    try:
        salt = hashed_password[:32]
        stored_hash = hashed_password[32:]
        pwd_hash = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt, 100000)
        return pwd_hash == stored_hash
    except:
        return False

def get_password_hash(password):
    """Hash a password using SHA256 with salt"""
    salt = os.urandom(32)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt + pwd_hash

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = users_db.get(email)
    if user is None:
        raise credentials_exception
    return user

# Routes
@app.get("/")
async def root():
    return {"message": "Email Classifier API (Mock - No MongoDB)", "version": "1.0.0"}

@app.get("/api/user/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    return {
        "username": current_user.get("username"),
        "email": current_user.get("email"),
        "imap_email": current_user.get("imap_email"),
        "imap_configured": current_user.get("imap_configured", False),
        "created_at": current_user.get("created_at")
    }

@app.post("/api/auth/signup")
async def signup(user: UserSignup):
    # Check if user exists
    if user.email in users_db:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Check username
    for u in users_db.values():
        if u.get("username") == user.username:
            raise HTTPException(status_code=400, detail="Username already taken")
    
    # Create new user
    hashed_password = get_password_hash(user.password)
    user_dict = {
        "_id": str(ObjectId()),
        "username": user.username,
        "email": user.email,
        "password": hashed_password,
        "created_at": datetime.utcnow().isoformat(),
        "imap_configured": False
    }
    
    users_db[user.email] = user_dict
    
    return {"message": "User created successfully", "user_id": user_dict["_id"]}

@app.post("/api/auth/login", response_model=Token)
async def login(user: UserLogin):
    # Find user
    db_user = users_db.get(user.email)
    if not db_user or not verify_password(user.password, db_user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "username": db_user["username"],
            "email": db_user["email"]
        }
    }

@app.post("/api/imap/setup")
async def setup_imap(config: IMAPConfig, current_user: dict = Depends(get_current_user)):
    # Update user's IMAP credentials
    current_user["imap_email"] = config.email
    current_user["imap_password"] = config.password
    current_user["imap_configured"] = True
    
    return {"message": "IMAP configuration saved successfully"}

@app.post("/api/imap/sync")
async def sync_emails(current_user: dict = Depends(get_current_user)):
    if not current_user.get("imap_configured"):
        raise HTTPException(status_code=400, detail="IMAP not configured")
    
    # Mock email sync
    user_id = current_user["_id"]
    mock_emails = [
        {
            "_id": str(ObjectId()),
            "user_id": user_id,
            "subject": "Welcome to Email Classifier",
            "from_": "team@emailclassifier.com",
            "date": datetime.utcnow().isoformat(),
            "body": "This is a test email.",
            "category": "Important",
            "confidence": 0.95
        }
    ]
    
    emails_db[user_id] = mock_emails
    return {"message": "Emails synced successfully", "synced_count": len(mock_emails)}

@app.get("/api/emails")
async def get_emails(current_user: dict = Depends(get_current_user)):
    user_id = current_user["_id"]
    emails = emails_db.get(user_id, [])
    return emails

@app.get("/api/notifications")
async def get_notifications(current_user: dict = Depends(get_current_user)):
    user_id = current_user["_id"]
    notifications = notifications_db.get(user_id, [])
    return notifications

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
