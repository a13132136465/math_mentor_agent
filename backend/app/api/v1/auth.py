from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.config import get_settings
from app.dependencies import get_student_repo
from app.repositories import StudentRepository
from app.services.auth import AuthService, get_auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

_DEV_AUTH_SUB = "dev-local-001"
_DEV_EMAIL = "dev@mathmentor.ai"
_DEV_DISPLAY_NAME = "Dev Student"


class GoogleAuthRequest(BaseModel):
    id_token: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    student_id: str
    display_name: str
    email: str


@router.post("/google", response_model=AuthResponse)
async def google_auth(
    body: GoogleAuthRequest,
    auth_service: AuthService = Depends(get_auth_service),
    students: StudentRepository = Depends(get_student_repo),
):
    """
    Exchange a Google ID token for a MathMentor JWT.
    Creates the student profile on first login.
    """
    try:
        claims = await auth_service.verify_google_token(body.id_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    student_doc = await students.upsert_by_auth_sub(
        auth_sub=claims["sub"],
        email=claims.get("email", ""),
        display_name=claims.get("name", claims.get("email", "Student")),
        avatar_url=claims.get("picture"),
    )

    student_id = str(student_doc["_id"])
    token = auth_service.create_access_token(
        student_id=student_id,
        auth_sub=claims["sub"],
        email=claims.get("email", ""),
        display_name=claims.get("name", "Student"),
    )

    return AuthResponse(
        access_token=token,
        student_id=student_id,
        display_name=claims.get("name", "Student"),
        email=claims.get("email", ""),
    )


@router.post("/dev-login", response_model=AuthResponse)
async def dev_login(
    auth_service: AuthService = Depends(get_auth_service),
    students: StudentRepository = Depends(get_student_repo),
):
    """
    Development-only bypass login. Returns a real signed JWT for a fixed dev student.
    Disabled in production.
    """
    settings = get_settings()
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev login is not available in production.",
        )

    student_doc = await students.upsert_by_auth_sub(
        auth_sub=_DEV_AUTH_SUB,
        email=_DEV_EMAIL,
        display_name=_DEV_DISPLAY_NAME,
    )

    student_id = str(student_doc["_id"])
    token = auth_service.create_access_token(
        student_id=student_id,
        auth_sub=_DEV_AUTH_SUB,
        email=_DEV_EMAIL,
        display_name=_DEV_DISPLAY_NAME,
    )

    return AuthResponse(
        access_token=token,
        student_id=student_id,
        display_name=_DEV_DISPLAY_NAME,
        email=_DEV_EMAIL,
    )
