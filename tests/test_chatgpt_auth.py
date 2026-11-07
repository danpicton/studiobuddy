import asyncio
import hashlib
import json
import time
from base64 import urlsafe_b64encode
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from studiobuddy.chatgpt_auth import AuthError, ChatGPTAuth


@pytest.fixture
def service():
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk["kid"] = "test"
    state = {
        "requests": [],
        "nonce": "",
        "scopes": "openid chatgpt.tokens.use.direct",
        "refreshes": 0,
    }

    def handle(request):
        state["requests"].append(request)
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": "https://auth.openai.com",
                    "jwks_uri": "https://auth.openai.com/jwks",
                    "revocation_endpoint": "https://auth.openai.com/revoke",
                },
            )
        if request.url.path == "/jwks":
            return httpx.Response(200, json={"keys": [jwk]})
        if request.url.path == "/revoke":
            return httpx.Response(state.get("revocation_status", 200))
        if request.url.path == "/api/accounts/oauth/token":
            data = parse_qs(request.content.decode())
            assert data["client_id"] == ["oaiapp_test"]
            assert data["resource"] == ["https://api.openai.com/v1"]
            if data["grant_type"] == ["refresh_token"]:
                state["refreshes"] += 1
                return httpx.Response(
                    200,
                    json={
                        "access_token": "refreshed",
                        "refresh_token": "rotated",
                        "expires_in": 3600,
                        "token_type": "Bearer",
                    },
                )
            challenge = (
                urlsafe_b64encode(hashlib.sha256(data["code_verifier"][0].encode()).digest())
                .rstrip(b"=")
                .decode()
            )
            assert challenge == state["challenge"]
            token = jwt.encode(
                {
                    "iss": "https://auth.openai.com",
                    "aud": "oaiapp_test",
                    "sub": "person",
                    "email": "test@example.com",
                    "exp": int(time.time()) + 600,
                    "nonce": state["nonce"],
                    **state.get("claims_override", {}),
                },
                rsa.generate_private_key(public_exponent=65537, key_size=2048)
                if state.get("bad_signature")
                else key,
                algorithm="RS256",
                headers={"kid": "test"},
            )
            return httpx.Response(
                200,
                json={
                    "access_token": "access-secret",
                    "refresh_token": "refresh-secret",
                    "id_token": token,
                    "expires_in": 3600,
                    "token_type": "Bearer",
                    "scope": state["scopes"],
                },
            )
        if request.url.path == "/v1/models":
            assert request.headers["Authorization"] == "Bearer access-secret"
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"slug": "test-model", "display_name": "Test model", "visibility": "list"},
                        {"slug": "hidden", "display_name": "Hidden", "visibility": "hide"},
                    ]
                },
            )
        raise AssertionError(request.url)

    async def browser(url):
        params = parse_qs(urlsplit(url).query)
        assert params["client_id"] == [
            "oaiapp_test" if state.get("returning") else "dynamic_agent_client"
        ]
        assert params["code_challenge_method"] == ["S256"]
        state["nonce"] = params["nonce"][0]
        state["challenge"] = params["code_challenge"][0]
        state["redirect_uri"] = params["redirect_uri"][0]
        async with httpx.AsyncClient(trust_env=False) as client:
            # An unrelated request must not consume the pending login.
            bad = await client.get(state["redirect_uri"], params={"state": "wrong", "code": "bad"})
            assert bad.status_code == 400
            response = await client.get(
                state["redirect_uri"],
                params={
                    "state": params["state"][0],
                    "code": "test-code",
                    "client_id": "oaiapp_test",
                },
            )
            assert response.status_code == 200

    return state, httpx.MockTransport(handle), browser


async def test_browser_sign_in_validates_and_stores_private_credentials(tmp_path, service):
    state, transport, browser = service
    path = tmp_path / "chatgpt-auth.json"
    auth = ChatGPTAuth(path, transport=transport)
    await auth.sign_in(browser)
    assert path.stat().st_mode & 0o777 == 0o600
    assert auth.account_label() == "test@example.com"
    assert await auth.access_token() == "access-secret"
    assert await auth.models() == [("test-model", "Test model")]
    saved = json.loads(path.read_text())
    assert saved["account"]["client_id"] == "oaiapp_test"
    assert saved["host_id"].startswith("urn:uuid:")
    assert state["redirect_uri"].startswith("http://127.0.0.1:")


async def test_missing_plan_permission_never_saves_access(tmp_path, service):
    state, transport, browser = service
    state["scopes"] = "openid"
    auth = ChatGPTAuth(tmp_path / "auth.json", transport=transport)
    with pytest.raises(AuthError, match="permission"):
        await auth.sign_in(browser)
    assert auth.account_label() == ""
    assert "access-secret" not in auth.path.read_text()


async def test_refresh_is_serialized_across_instances(tmp_path, service):
    state, transport, browser = service
    path = tmp_path / "auth.json"
    auth = ChatGPTAuth(path, transport=transport)
    await auth.sign_in(browser)
    data = json.loads(path.read_text())
    data["account"]["expires_at"] = 0
    path.write_text(json.dumps(data))
    other = ChatGPTAuth(path, transport=transport)
    assert await asyncio.gather(auth.access_token(), other.access_token()) == ["refreshed"] * 2
    assert state["refreshes"] == 1
    assert json.loads(path.read_text())["account"]["refresh_token"] == "rotated"


async def test_signout_revokes_then_clears_tokens_but_keeps_registration(tmp_path, service):
    state, transport, browser = service
    auth = ChatGPTAuth(tmp_path / "auth.json", transport=transport)
    await auth.sign_in(browser)
    await auth.sign_out()
    assert any(r.url.path == "/revoke" for r in state["requests"])
    saved = json.loads(auth.path.read_text())
    assert saved["account"]["client_id"] == "oaiapp_test"
    assert "access_token" not in saved["account"]
    assert "refresh_token" not in saved["account"]
    assert "id_token" not in saved["account"]
    with pytest.raises(AuthError, match="Continue with ChatGPT"):
        await auth.access_token()


@pytest.mark.parametrize(
    "override",
    [
        {"nonce": "wrong"},
        {"aud": "other-app"},
        {"iss": "https://evil.example"},
        {"exp": 1},
    ],
)
async def test_invalid_identity_is_not_saved(tmp_path, service, override):
    state, transport, browser = service
    state["claims_override"] = override
    auth = ChatGPTAuth(tmp_path / "auth.json", transport=transport)
    with pytest.raises(AuthError):
        await auth.sign_in(browser)
    assert "access-secret" not in auth.path.read_text()


async def test_cancelled_login_closes_callback_listener(tmp_path):
    ready = asyncio.Event()
    callback = ""

    async def browser(url):
        nonlocal callback
        callback = parse_qs(urlsplit(url).query)["redirect_uri"][0]
        ready.set()

    auth = ChatGPTAuth(tmp_path / "auth.json")
    task = asyncio.create_task(auth.sign_in(browser))
    await ready.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with httpx.AsyncClient(trust_env=False) as client:
        with pytest.raises(httpx.ConnectError):
            await client.get(callback)
    assert auth.account_label() == ""


async def test_forged_signature_is_rejected(tmp_path, service):
    state, transport, browser = service
    state["bad_signature"] = True
    auth = ChatGPTAuth(tmp_path / "auth.json", transport=transport)
    with pytest.raises(AuthError):
        await auth.sign_in(browser)
    assert "access-secret" not in auth.path.read_text()


async def test_returning_login_reuses_registration_and_rejects_other_identity(tmp_path, service):
    state, transport, browser = service
    auth = ChatGPTAuth(tmp_path / "auth.json", transport=transport)
    await auth.sign_in(browser)
    state["returning"] = True
    await auth.sign_in(browser)
    before = auth.path.read_text()
    state["claims_override"] = {"sub": "another-person"}
    with pytest.raises(AuthError, match="same ChatGPT account"):
        await auth.sign_in(browser)
    assert auth.path.read_text() == before


async def test_failed_revocation_clears_local_tokens_and_explains_recovery(tmp_path, service):
    state, transport, browser = service
    auth = ChatGPTAuth(tmp_path / "auth.json", transport=transport)
    await auth.sign_in(browser)
    state["revocation_status"] = 503
    with pytest.raises(AuthError, match="remote revocation was not confirmed"):
        await auth.sign_out()
    assert auth.account_label() == ""
    assert "access-secret" not in auth.path.read_text()
    assert len([r for r in state["requests"] if r.url.path == "/revoke"]) == 2
