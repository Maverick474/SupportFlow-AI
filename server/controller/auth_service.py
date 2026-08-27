import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from pwdlib import PasswordHash

from controller.config import Settings
from models.auth import RegisterRequest, TokenPair, UserPublic


class AuthenticationError(Exception):
    pass


class UserAlreadyExistsError(Exception):
    pass


class AuthService:
    def __init__(self, database: Any, settings: Settings) -> None:
        self.users = database["users"]
        self.sessions = database["sessions"]
        self.settings = settings
        self.password_hash = PasswordHash.recommended()

    async def ensure_indexes(self) -> None:
        await self.users.create_index("email", unique=True)
        await self.sessions.create_index("token_hash", unique=True)
        await self.sessions.create_index("expires_at", expireAfterSeconds=0)

    async def register(self, request: RegisterRequest) -> TokenPair:
        now = datetime.now(UTC)
        document = {
            "email": str(request.email).lower(),
            "password_hash": self.password_hash.hash(request.password),
            "full_name": request.full_name.strip(),
            "workspace_id": str(request.workspace_id),
            "role": "customer",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = await self.users.insert_one(document)
        except DuplicateKeyError as exc:
            raise UserAlreadyExistsError("An account already uses this email.") from exc
        document["_id"] = result.inserted_id
        return await self._issue_token_pair(document)

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self.users.find_one({"email": email.lower()})
        if (
            user is None
            or not user.get("is_active", True)
            or not self.password_hash.verify(password, user["password_hash"])
        ):
            raise AuthenticationError("Invalid email or password.")
        return await self._issue_token_pair(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        token_hash = self._hash_refresh_token(refresh_token)
        session = await self.sessions.find_one_and_delete(
            {
                "token_hash": token_hash,
                "expires_at": {"$gt": datetime.now(UTC)},
            }
        )
        if session is None:
            raise AuthenticationError("Refresh session is invalid or expired.")

        user = await self.users.find_one(
            {"_id": session["user_id"], "is_active": True}
        )
        if user is None:
            raise AuthenticationError("User account is unavailable.")
        return await self._issue_token_pair(user)

    async def logout(self, refresh_token: str) -> None:
        await self.sessions.delete_one(
            {"token_hash": self._hash_refresh_token(refresh_token)}
        )

    async def user_from_access_token(self, token: str) -> UserPublic:
        try:
            payload = jwt.decode(
                token,
                self.settings.jwt_key,
                algorithms=[self.settings.jwt_algorithm],
            )
            if payload.get("type") != "access":
                raise AuthenticationError("Invalid token type.")
            user_id = ObjectId(payload["sub"])
        except (jwt.PyJWTError, KeyError, ValueError) as exc:
            raise AuthenticationError("Access token is invalid or expired.") from exc

        user = await self.users.find_one({"_id": user_id, "is_active": True})
        if user is None:
            raise AuthenticationError("User account is unavailable.")
        return self._public_user(user)

    async def _issue_token_pair(self, user: dict[str, Any]) -> TokenPair:
        now = datetime.now(UTC)
        access_expires = now + timedelta(
            minutes=self.settings.access_token_expire_minutes
        )
        access_token = jwt.encode(
            {
                "sub": str(user["_id"]),
                "email": user["email"],
                "workspace_id": user["workspace_id"],
                "role": user["role"],
                "type": "access",
                "jti": uuid4().hex,
                "iat": now,
                "exp": access_expires,
            },
            self.settings.jwt_key,
            algorithm=self.settings.jwt_algorithm,
        )

        refresh_token = secrets.token_urlsafe(64)
        await self.sessions.insert_one(
            {
                "user_id": user["_id"],
                "token_hash": self._hash_refresh_token(refresh_token),
                "created_at": now,
                "expires_at": now
                + timedelta(days=self.settings.refresh_token_expire_days),
            }
        )

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.settings.access_token_expire_minutes * 60,
            user=self._public_user(user),
        )

    @staticmethod
    def _hash_refresh_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _public_user(user: dict[str, Any]) -> UserPublic:
        return UserPublic(
            id=str(user["_id"]),
            email=user["email"],
            full_name=user["full_name"],
            workspace_id=user["workspace_id"],
            role=user["role"],
        )
