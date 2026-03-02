from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.security import decode_token, parse_admin_ids

bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    user_id: int
    is_admin: bool


def _dev_header_fallback(x_user_id: str | None) -> CurrentUser | None:
    if settings.app_env != 'dev' or not x_user_id:
        return None
    if not x_user_id.isdigit():
        raise HTTPException(status_code=400, detail='Invalid X-User-Id header')
    uid = int(x_user_id)
    return CurrentUser(user_id=uid, is_admin=(uid in parse_admin_ids()))


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    x_user_id: str | None = Header(default=None),
) -> CurrentUser:
    fallback = _dev_header_fallback(x_user_id)
    if fallback:
        return fallback

    if not credentials or credentials.scheme.lower() != 'bearer':
        raise HTTPException(status_code=401, detail='Missing bearer token')

    try:
        payload = decode_token(credentials.credentials, expected_type='access')
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail='Invalid access token') from exc

    sub = payload.get('sub')
    if not sub or not str(sub).isdigit():
        raise HTTPException(status_code=401, detail='Invalid token subject')

    uid = int(sub)
    is_admin = bool(payload.get('adm', False)) or uid in parse_admin_ids()
    return CurrentUser(user_id=uid, is_admin=is_admin)


def current_user_id(user: CurrentUser = Depends(current_user)) -> int:
    return user.user_id


def require_admin(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail='Admin access required')
    return user
