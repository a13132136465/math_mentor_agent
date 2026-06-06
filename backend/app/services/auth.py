"""
Auth service — Google ID token verification → internal JWT issuance.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import structlog
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import get_settings

logger = structlog.get_logger(__name__)

GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"


class TokenPayload(BaseModel):
    sub: str          # student_id (MongoDB ObjectId as string)
    auth_sub: str     # Google OAuth subject
    email: str
    display_name: str
    exp: int


class AuthService:
    def __init__(self) -> None:
        self._settings = get_settings()

    # ── Google ID token verification ──────────────────────────────

    async def verify_google_token(self, id_token: str) -> dict:
        """
        Verify a Google ID token via Google's tokeninfo endpoint.
        Returns the decoded claims dict or raises ValueError.
        """
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                GOOGLE_TOKEN_INFO_URL, params={"id_token": id_token}
            )

        if resp.status_code != 200:
            raise ValueError(f"Google token verification failed: {resp.text}")

        claims = resp.json()

        if claims.get("aud") != self._settings.google_client_id:
            raise ValueError("Token audience mismatch")

        if not claims.get("email_verified", False):
            raise ValueError("Email not verified")

        return claims

    # ── Internal JWT ──────────────────────────────────────────────

    def create_access_token(
        self,
        student_id: str,
        auth_sub: str,
        email: str,
        display_name: str,
    ) -> str:
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=self._settings.jwt_expire_minutes)
        payload = {
            "sub": student_id,
            "auth_sub": auth_sub,
            "email": email,
            "display_name": display_name,
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
        }
        return jwt.encode(
            payload,
            self._settings.jwt_secret,
            algorithm=self._settings.jwt_algorithm,
        )

    def decode_access_token(self, token: str) -> TokenPayload:
        try:
            payload = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=[self._settings.jwt_algorithm],
            )
            return TokenPayload(**payload)
        except JWTError as exc:
            raise ValueError(f"Invalid token: {exc}") from exc


def get_auth_service() -> AuthService:
    return AuthService()
