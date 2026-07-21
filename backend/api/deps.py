from typing import Generator, Optional, List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import User
from api.security import decode_access_token
from pydantic import BaseModel, Field

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Pydantic Schemas for Requests/Responses
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    department: Optional[str] = Field(default="Engineering", description="Department name")
    role: Optional[str] = Field(default="employee", description="User role: super_admin, department_manager, team_lead, employee, guest")
    team: Optional[str] = Field(default=None, description="Optional team name")
    designation: Optional[str] = Field(default=None, description="Optional job designation")

class UserResponse(BaseModel):
    id: int
    username: str
    department: str
    role: str
    team: Optional[str] = None
    designation: Optional[str] = None
    clearance_level: str
    full_name: Optional[str] = None
    contact_details: Optional[str] = None
    email: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, description="Employee Full Name")
    contact_details: Optional[str] = Field(default=None, description="Contact Phone / Address")
    email: Optional[str] = Field(default=None, description="Contact Email")

class PasswordChange(BaseModel):
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=6, description="New password")

class AdminUserUpdate(BaseModel):
    username: Optional[str] = Field(default=None, min_length=3, max_length=50)
    role: Optional[str] = Field(default=None)
    department: Optional[str] = Field(default=None)
    clearance_level: Optional[str] = Field(default=None)
    full_name: Optional[str] = Field(default=None)
    contact_details: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)

class Token(BaseModel):
    access_token: str
    token_type: str

class QueryRequest(BaseModel):
    query: str = Field(..., description="Query input to run in the multi-agent system")
    conversation_id: Optional[int] = Field(default=None, description="Optional conversation history ID to attach to")

class WorkflowRunRequest(BaseModel):
    query: str
    agent_nodes: list[str] = Field(default=[], description="Specific sequence of agents to run")


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
        
    username = payload.get("sub")
    if username is None:
        raise credentials_exception
        
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact Super Admin."
        )
        
    return user


def require_roles(allowed_roles: List[str]):
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.lower() not in [r.lower() for r in allowed_roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation restricted to roles: {', '.join(allowed_roles)}"
            )
        return current_user
    return role_checker
