"""JWT tokens carry and strictly verify issuer (iss) and audience (aud) claims.

These run in TIER 2 (token crypto only; no DB/network). They prove the added
security property and pin the adversarial-review correction that ``audience=``
alone does NOT make ``aud`` mandatory in python-jose -- presence is enforced via
the boolean flags ``options={'require_aud': True, 'require_iss': True}`` (a
PyJWT-style ``options={'require': [...]}`` list is silently ignored by jose).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from src.auth.security import (
    _get_jwt_audience,
    _get_jwt_issuer,
    _get_signing_key,
    _get_verification_key,
    create_access_token,
    decode_token,
    get_algorithm,
)


def test_access_token_carries_iss_and_aud():
    token = create_access_token(uuid.uuid4(), uuid.uuid4(), "admin")
    claims = jwt.decode(
        token,
        _get_verification_key(),
        algorithms=[get_algorithm()],
        audience=_get_jwt_audience(),
        issuer=_get_jwt_issuer(),
    )
    assert claims["iss"] == _get_jwt_issuer()
    assert claims["aud"] == _get_jwt_audience()


def test_decode_round_trips_and_strips_aud_iss():
    uid, oid = uuid.uuid4(), uuid.uuid4()
    payload = decode_token(create_access_token(uid, oid, "member"))
    assert payload.sub == str(uid)
    assert payload.org_id == str(oid)
    assert payload.type == "access"
    # TokenPayload has no aud/iss fields; they were validated then stripped.
    assert not hasattr(payload, "aud")
    assert not hasattr(payload, "iss")


def _forge(*, aud="__default__", iss="__default__", omit=()):
    claims = {
        "sub": str(uuid.uuid4()),
        "org_id": str(uuid.uuid4()),
        "role": "admin",
        "type": "access",
        "jti": str(uuid.uuid4()),
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "iss": _get_jwt_issuer() if iss == "__default__" else iss,
        "aud": _get_jwt_audience() if aud == "__default__" else aud,
    }
    for key in omit:
        claims.pop(key, None)
    return jwt.encode(claims, _get_signing_key(), algorithm=get_algorithm())


def test_decode_rejects_wrong_audience():
    with pytest.raises(ValueError, match="Invalid token"):
        decode_token(_forge(aud="some-other-service"))


def test_decode_rejects_wrong_issuer():
    with pytest.raises(ValueError, match="Invalid token"):
        decode_token(_forge(iss="some-other-issuer"))


def test_decode_rejects_missing_audience_in_strict_mode():
    # The key correction: a correct-iss token with NO aud claim must be REJECTED
    # (it was wrongly accepted before adding options={'require': [...]}).
    with pytest.raises(ValueError, match="Invalid token"):
        decode_token(_forge(omit=("aud",)))


def test_decode_rejects_missing_issuer_in_strict_mode():
    with pytest.raises(ValueError, match="Invalid token"):
        decode_token(_forge(omit=("iss",)))
