from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.config import settings
from app.deps import current_user
from app.security import create_access_token


def _save_settings() -> tuple[str, str, str]:
    return settings.app_env, settings.admin_ids, settings.jwt_secret


def _restore_settings(saved: tuple[str, str, str]) -> None:
    settings.app_env, settings.admin_ids, settings.jwt_secret = saved


def test_current_user_dev_header_fallback():
    saved = _save_settings()
    settings.app_env = 'dev'
    settings.admin_ids = '100,200'
    settings.jwt_secret = 'test-secret'
    try:
        user = current_user(credentials=None, x_user_id='200')
        assert user.user_id == 200
        assert user.is_admin is True
    finally:
        _restore_settings(saved)


def test_current_user_bearer_token():
    saved = _save_settings()
    settings.app_env = 'prod'
    settings.admin_ids = ''
    settings.jwt_secret = 'test-secret'
    try:
        token = create_access_token(user_id=42, is_admin=False)
        creds = HTTPAuthorizationCredentials(scheme='Bearer', credentials=token)
        user = current_user(credentials=creds, x_user_id=None)
        assert user.user_id == 42
        assert user.is_admin is False
    finally:
        _restore_settings(saved)


def test_current_user_missing_auth():
    saved = _save_settings()
    settings.app_env = 'prod'
    settings.jwt_secret = 'test-secret'
    try:
        try:
            current_user(credentials=None, x_user_id=None)
            assert False, 'expected HTTPException'
        except HTTPException as exc:
            assert exc.status_code == 401
    finally:
        _restore_settings(saved)
