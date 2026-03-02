import jwt

from app import security
from app.config import settings


def test_access_token_roundtrip():
    settings.jwt_secret = 'test-secret'
    token = security.create_access_token(user_id=123, is_admin=True)
    payload = security.decode_token(token, expected_type='access')
    assert payload['sub'] == '123'
    assert payload['adm'] is True


def test_refresh_token_roundtrip_and_hash():
    settings.jwt_secret = 'test-secret'
    token, _ = security.create_refresh_token(user_id=777)
    payload = security.decode_token(token, expected_type='refresh')
    assert payload['sub'] == '777'

    h1 = security.hash_refresh_token(token)
    h2 = security.hash_refresh_token(token)
    assert h1 == h2
    assert len(h1) == 64


def test_decode_rejects_wrong_type():
    settings.jwt_secret = 'test-secret'
    access = security.create_access_token(user_id=1, is_admin=False)
    try:
        security.decode_token(access, expected_type='refresh')
        assert False, 'expected InvalidTokenError'
    except jwt.InvalidTokenError:
        assert True
