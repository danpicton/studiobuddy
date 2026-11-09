"""Personal desktop ChatGPT OAuth. Credentials never enter settings, SQLite or logs."""

import asyncio
import fcntl
import hashlib
import json
import os
import secrets
import tempfile
import time
import uuid
from base64 import urlsafe_b64encode
from contextlib import asynccontextmanager
from functools import wraps
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import jwt

ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
TOKEN_URL = ISSUER + "/api/accounts/oauth/token"
PLAN_SCOPE = "chatgpt.tokens.use.direct"


class AuthError(Exception):
    """Only locally authored messages safe for the UI."""


def safe_errors(method):
    @wraps(method)
    async def wrapped(*args, **kwargs):
        try:
            return await method(*args, **kwargs)
        except AuthError:
            raise
        except Exception:  # noqa: BLE001 - never surface tokens or remote bodies
            raise AuthError(
                "ChatGPT sign-in request failed. Check your connection and try again."
            ) from None

    return wrapped


class ChatGPTAuth:
    def __init__(self, path, transport=None):
        self.path = Path(path)
        self.transport = transport

    def _load(self):
        if not self.path.exists():
            return {"host_id": "urn:uuid:" + str(uuid.uuid4()), "account": {}}
        return json.loads(self.path.read_text())

    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".chatgpt-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(data, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @asynccontextmanager
    async def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(str(self.path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(0.05)
            yield
        finally:
            os.close(fd)

    def account_label(self):
        account = self._load()["account"]
        return (
            account.get("email", account.get("subject", "")) if account.get("access_token") else ""
        )

    def _client(self):
        return httpx.AsyncClient(
            transport=self.transport, timeout=20, follow_redirects=False, trust_env=False
        )

    async def _discovery(self, client):
        response = await client.get(ISSUER + "/.well-known/openid-configuration")
        response.raise_for_status()
        data = response.json()
        if data["issuer"] != ISSUER:
            raise AuthError("ChatGPT identity provider could not be verified.")
        for key in ("jwks_uri", "revocation_endpoint"):
            url = urlsplit(data[key])
            if url.scheme != "https" or url.netloc != "auth.openai.com" or url.fragment:
                raise AuthError("ChatGPT identity provider could not be verified.")
        return data

    async def _validate(self, client, tokens, client_id, nonce):
        discovery = await self._discovery(client)
        response = await client.get(discovery["jwks_uri"])
        response.raise_for_status()
        header = jwt.get_unverified_header(tokens["id_token"])
        key = next(k for k in response.json()["keys"] if k.get("kid") == header.get("kid"))
        claims = jwt.decode(
            tokens["id_token"],
            jwt.PyJWK.from_dict(key).key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=ISSUER,
            options={"require": ["exp", "iss", "aud", "sub", "nonce"]},
        )
        if not secrets.compare_digest(claims["nonce"], nonce):
            raise AuthError("ChatGPT sign-in identity could not be verified. Try again.")
        return claims

    def _merge_tokens(self, account, tokens):
        scopes = tokens.get("scope", " ".join(account.get("scopes", []))).split()
        if PLAN_SCOPE not in scopes:
            raise AuthError("ChatGPT plan permission was not granted. Continue with ChatGPT again.")
        if tokens.get("token_type", "").lower() != "bearer" or not tokens.get("access_token"):
            raise AuthError("ChatGPT returned an invalid sign-in response. Try again.")
        result = {
            **account,
            "access_token": tokens["access_token"],
            "scopes": scopes,
            "expires_at": time.time() + float(tokens["expires_in"]),
        }
        for key in ("refresh_token", "id_token"):
            if tokens.get(key):
                result[key] = tokens[key]
        return result

    @safe_errors
    async def sign_in(self, open_url):
        # Serialize login/refresh/revocation across windows and processes.
        async with self._locked():
            data = self._load()
            self._save(data)  # Persist the installation identity before registration.
            account = data["account"]
            client_id = account.get("client_id", "dynamic_agent_client")
            state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
            challenge = (
                urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            )
            callback = asyncio.get_running_loop().create_future()
            handlers = set()

            async def receive(reader, writer):
                handlers.add(asyncio.current_task())
                try:
                    request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
                    method, target, _ = request.split(b"\r\n", 1)[0].decode("ascii").split(" ")
                    parsed = urlsplit(target)
                    query = parse_qs(parsed.query)
                    valid = (
                        method == "GET"
                        and parsed.path == "/auth/callback"
                        and query.get("state") == [state]
                        and not callback.done()
                    )
                    status = "200 OK" if valid else "400 Bad Request"
                    if valid:
                        callback.set_result(query)
                    body = (
                        b"Return to Studio Buddy to finish sign-in."
                        if valid
                        else b"Invalid callback."
                    )
                    writer.write(
                        f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: {len(body)}\r\n\r\n".encode()
                        + body
                    )
                    await writer.drain()
                except (
                    ValueError,
                    UnicodeError,
                    TimeoutError,
                    asyncio.IncompleteReadError,
                    asyncio.LimitOverrunError,
                    ConnectionError,
                ):
                    pass
                finally:
                    writer.close()
                    handlers.discard(asyncio.current_task())

            server = await asyncio.start_server(receive, "127.0.0.1", 0, limit=8192)
            redirect = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/auth/callback"
            params = {
                "client_id": client_id,
                "ext_agent_host_id": data["host_id"],
                "response_type": "code",
                "redirect_uri": redirect,
                "scope": "openid profile email offline_access resource.invoke " + PLAN_SCOPE,
                "resource": RESOURCE,
                "state": state,
                "nonce": nonce,
                "code_challenge_method": "S256",
                "code_challenge": challenge,
            }
            if client_id == "dynamic_agent_client":
                params["agent_name_hint"] = "Studio Buddy"
            try:
                async with server, asyncio.timeout(180):
                    await open_url(ISSUER + "/api/accounts/authorize?" + urlencode(params))
                    query = await callback
            finally:
                for task in list(handlers):
                    task.cancel()
                await asyncio.gather(*handlers, return_exceptions=True)
            if "error" in query:
                raise AuthError("ChatGPT sign-in was declined. No connection was changed.")
            issued_id = query.get("client_id", [client_id])[0]
            if issued_id == "dynamic_agent_client" or (
                client_id != "dynamic_agent_client" and issued_id != client_id
            ):
                raise AuthError("ChatGPT registration did not match. Try signing in again.")
            async with self._client() as client:
                response = await client.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": issued_id,
                        "code": query["code"][0],
                        "code_verifier": verifier,
                        "redirect_uri": redirect,
                        "resource": RESOURCE,
                    },
                )
                response.raise_for_status()
                tokens = response.json()
                claims = await self._validate(client, tokens, issued_id, nonce)
            if account.get("subject") and claims["sub"] != account["subject"]:
                raise AuthError("Sign in with the same ChatGPT account registered on this desktop.")
            updated = self._merge_tokens(
                {
                    "client_id": issued_id,
                    "subject": claims["sub"],
                    "email": claims.get("email", claims["sub"]),
                },
                tokens,
            )
            self._save({**data, "account": updated})
            return self.account_label()

    @safe_errors
    async def access_token(self):
        async with self._locked():
            data = self._load()
            account = data["account"]
            if not account.get("access_token"):
                raise AuthError("Choose Continue with ChatGPT to connect your subscription.")
            if account["expires_at"] > time.time() + 60:
                return account["access_token"]
            if not account.get("refresh_token"):
                raise AuthError("Your ChatGPT sign-in expired. Choose Continue with ChatGPT.")
            async with self._client() as client:
                response = await client.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "client_id": account["client_id"],
                        "refresh_token": account["refresh_token"],
                        "resource": RESOURCE,
                    },
                )
                if response.status_code in (400, 401, 403):
                    raise AuthError("Your ChatGPT sign-in expired. Choose Continue with ChatGPT.")
                response.raise_for_status()
                updated = self._merge_tokens(account, response.json())
            self._save({**data, "account": updated})
            return updated["access_token"]

    @safe_errors
    async def models(self):
        token = await self.access_token()
        async with self._client() as client:
            response = await client.get(
                RESOURCE + "/models", headers={"Authorization": "Bearer " + token}
            )
            response.raise_for_status()
            return [
                (m["slug"], m["display_name"])
                for m in response.json()["models"]
                if m.get("visibility") == "list"
            ]

    @safe_errors
    async def sign_out(self):
        async with self._locked():
            data = self._load()
            account = data["account"]
            revoked = not account.get("refresh_token")
            try:
                if not revoked:
                    async with self._client() as client:
                        discovery = await self._discovery(client)
                        for attempt in range(2):
                            try:
                                response = await client.post(
                                    discovery["revocation_endpoint"],
                                    data={
                                        "token": account["refresh_token"],
                                        "token_type_hint": "refresh_token",
                                        "client_id": account["client_id"],
                                    },
                                )
                                revoked = response.status_code == 200
                                if revoked:
                                    break
                            except httpx.HTTPError:
                                pass
                            if attempt == 0:
                                await asyncio.sleep(0.5)
            finally:
                for key in ("access_token", "refresh_token", "id_token", "expires_at", "scopes"):
                    account.pop(key, None)
                self._save(data)
            if not revoked:
                raise AuthError(
                    "Signed out locally; remote revocation was not confirmed. Disconnect Studio Buddy in ChatGPT Settings → Usage."
                )
            return "Signed out of ChatGPT."
