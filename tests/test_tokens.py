from datetime import timedelta

import pytest

from app.core.tokens import InvalidTokenError, create_access_token, decode_access_token
from tests.helpers import make_jwt


def test_token_roundtrip() -> None:
    token = create_access_token(42)

    assert decode_access_token(token) == 42


def test_expired_token() -> None:
    token = make_jwt(1, expires_in=timedelta(seconds=-10))

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


