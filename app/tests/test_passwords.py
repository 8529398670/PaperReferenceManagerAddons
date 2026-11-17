"""Password sign-in and two-factor, through the real routes: the toggles, the
per-account block, every way of signing in being asked for a code, and the
answers that must not say which part was wrong."""
from __future__ import annotations

import asyncio
import json
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

try:
    from starlette.testclient import TestClient
except (ImportError, RuntimeError) as missing:  # Starlette raises RuntimeError
    raise unittest.SkipTest(f"needs httpx2 (pip install httpx2): {missing}")

from app.core import assets, db, encryption, language
from app.core.static_files import StaticServer
from app.main import build_app
from app.models import credentials, login_tokens, users
from app.models import two_factor
from app.routes import two_factor as two_factor_routes
from app.models.attempts import AttemptGuard
from app.tests.support import new_holder

BASE_URL = "https://testserver"


def code_for(secret: str, step_offset: int = 0) -> str:
    step = int(time.time()) // encryption.TOTP_PERIOD_SECONDS + step_offset
    return encryption.totp_code(secret, step)


class AuthRoutesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.holder, _ = new_holder(self, app_dir=str(Path(directory.name) / "data"))
        self.cfg = self.holder.boot()
        self.cfg.app_dir.mkdir(parents=True, exist_ok=True)
        (self.cfg.app_dir / "logs").mkdir(exist_ok=True)
        self.set_config(rate_limit_max=100000, rate_limit_signin_max=100000)
        self.set_config(two_factor_enabled=True)
        # encrypt_at_rest off, so a test can see what a record really holds.
        self.store = db.open_store(self.cfg.database_path, self.cfg.secret_key, False)
        bundle = assets.resolve(self.cfg.static_dir, self.cfg.language_file)
        app = build_app(self.holder, self.store, language.parse(bundle.language_yaml), StaticServer(bundle.static_dir))
        self.owner = users.create_user(self.store, "Owner", users.ROLE_ADMIN)
        self.alice = users.create_user(self.store, "Alice", users.ROLE_USER)
        self.app = app
        self.client = self.new_client()
        # Guards are per process, so each test starts with clean counts.
        two_factor_routes.CODES = AttemptGuard()

    def set_config(self, **changes: object) -> None:
        self.holder._current = replace(self.holder.get(), **changes)

    def new_client(self) -> TestClient:
        return TestClient(self.app, base_url=BASE_URL)

    def sign_in_with_link(self, user_id: int, client: TestClient | None = None) -> TestClient:
        client = client or self.new_client()
        credential = login_tokens.issue_login_token(self.store, user_id, 600)
        response = client.post("/api/login", json={"credential": credential})
        self.assertEqual(response.status_code, 200)
        return client

    def csrf(self, client: TestClient) -> str:
        return client.get("/api/me").json()["csrf_token"]

    def enrol(self, client: TestClient) -> tuple[str, list[str]]:
        token = self.csrf(client)
        secret = client.post("/api/account/two-factor/start", json={"csrf_token": token}).json()["secret"]
        response = client.post("/api/account/two-factor/confirm", json={"code": code_for(secret), "csrf_token": token})
        self.assertEqual(response.status_code, 200)
        return secret, response.json()["recovery_codes"]

class TwoFactorTest(AuthRoutesTestCase):
    def test_rfc_6238_vector(self) -> None:
        # Appendix B of the RFC, seed "12345678901234567890", t = 59. The RFC
        # shows eight digits, 94287082; six is the same value's tail.
        self.assertEqual(encryption.totp_code("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 59 // 30), "287082")

    def test_the_secret_is_encrypted_on_its_own(self) -> None:
        alice = self.sign_in_with_link(self.alice.id)
        secret, _ = self.enrol(alice)
        # This store has encrypt_at_rest off, so the record is plain JSON.
        record = self.store.get(db.BUCKET_USERS, self.alice.id)
        self.assertNotIn(secret, str(record))
        self.assertEqual(encryption.xchacha_decrypt_string(encryption.subkey(self.cfg.secret_key, encryption.PURPOSE_TOTP), record["totp_secret"]), secret)

    def test_a_login_link_asks_for_the_code(self) -> None:
        alice = self.sign_in_with_link(self.alice.id)
        secret, _ = self.enrol(alice)
        fresh = self.new_client()
        credential = login_tokens.issue_login_token(self.store, self.alice.id, 600)
        response = fresh.post("/api/login", json={"credential": credential}).json()
        self.assertTrue(response["two_factor"])
        self.assertEqual(fresh.get("/api/me").status_code, 401)

        wrong = fresh.post("/api/login/two-factor", json={"challenge": response["challenge"], "code": "000000"})
        self.assertEqual(wrong.json(), {"error": "two_factor_wrong"})
        right = fresh.post("/api/login/two-factor", json={"challenge": response["challenge"], "code": code_for(secret, 1)})
        self.assertEqual(right.status_code, 200)
        self.assertEqual(fresh.get("/api/me").json()["id"], self.alice.id)

    def test_a_code_works_once(self) -> None:
        alice = self.sign_in_with_link(self.alice.id)
        secret, _ = self.enrol(alice)
        code = code_for(secret, 1)
        for expected in (200, 403):
            challenge = login_tokens.redeem_login_token(
                self.store, login_tokens.issue_login_token(self.store, self.alice.id, 600),
                login_rules(self.cfg),
            ).challenge
            response = self.new_client().post("/api/login/two-factor", json={"challenge": challenge, "code": code})
            self.assertEqual(response.status_code, expected)

    def test_a_challenge_works_once(self) -> None:
        alice = self.sign_in_with_link(self.alice.id)
        _, recovery = self.enrol(alice)
        challenge = self.new_challenge()
        self.assertEqual(self.finish(challenge, recovery[0]).status_code, 200)
        self.assertEqual(self.finish(challenge, recovery[1]).json(), {"error": "challenge_invalid"})

    def new_challenge(self) -> str:
        return login_tokens.redeem_login_token(
            self.store, login_tokens.issue_login_token(self.store, self.alice.id, 600), login_rules(self.cfg)
        ).challenge

    def finish(self, challenge: str, code: str) -> object:
        return self.new_client().post("/api/login/two-factor", json={"challenge": challenge, "code": code})

    def test_a_recovery_code_works_once(self) -> None:
        alice = self.sign_in_with_link(self.alice.id)
        _, recovery = self.enrol(alice)
        self.assertEqual(len(recovery), two_factor.RECOVERY_CODE_COUNT)
        self.assertEqual(self.finish(self.new_challenge(), recovery[0].lower()).status_code, 200)
        self.assertEqual(self.finish(self.new_challenge(), recovery[0]).status_code, 403)

    def test_wrong_codes_lock(self) -> None:
        alice = self.sign_in_with_link(self.alice.id)
        secret, _ = self.enrol(alice)
        challenge = self.new_challenge()
        for _ in range(5):
            self.finish(challenge, "000000")
        self.assertEqual(self.finish(challenge, code_for(secret, 1)).json(), {"error": "two_factor_locked"})

    def test_parallel_wrong_codes_cannot_pass_the_lockout(self) -> None:
        """S4: twenty wrong codes sent at once get at most five evaluated. The
        lockout used to be checked before the code and recorded after it, so
        parallel guesses all slipped past the check."""
        alice = self.sign_in_with_link(self.alice.id)
        self.enrol(alice)
        challenge = self.new_challenge()
        body = json.dumps({"challenge": challenge, "code": "000000"}).encode()

        async def post() -> int:
            sent: list[dict] = []
            received = False

            async def receive() -> dict:
                nonlocal received
                if received:
                    await asyncio.sleep(3600)
                received = True
                return {"type": "http.request", "body": body, "more_body": False}

            async def send(message: dict) -> None:
                sent.append(message)

            scope = {
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
                "scheme": "https", "path": "/api/login/two-factor", "raw_path": b"/api/login/two-factor",
                "query_string": b"", "root_path": "", "client": ("127.0.0.1", 50000), "server": ("testserver", 443),
                "headers": [(b"content-type", b"application/json"), (b"host", b"testserver")],
            }
            await self.app(scope, receive, send)
            return sent[0]["status"]

        async def all_at_once() -> list[int]:
            return await asyncio.gather(*(post() for _ in range(20)))

        statuses = asyncio.run(all_at_once())
        self.assertLessEqual(statuses.count(403), 5, statuses)

    def test_turning_it_off_needs_a_code(self) -> None:
        alice = self.sign_in_with_link(self.alice.id)
        secret, _ = self.enrol(alice)
        token = self.csrf(alice)
        refused = alice.post("/api/account/two-factor/disable", json={"code": "", "csrf_token": token})
        self.assertEqual(refused.status_code, 403)
        done = alice.post("/api/account/two-factor/disable", json={"code": code_for(secret, 1), "csrf_token": token})
        self.assertEqual(done.status_code, 200)
        self.sign_in_with_link(self.alice.id)

    def test_the_toggle_stops_asking_and_restores(self) -> None:
        alice = self.sign_in_with_link(self.alice.id)
        self.enrol(alice)
        self.set_config(two_factor_enabled=False)
        self.sign_in_with_link(self.alice.id)
        token = self.csrf(alice)
        self.assertEqual(alice.post("/api/account/two-factor/start", json={"csrf_token": token}).status_code, 404)
        self.set_config(two_factor_enabled=True)
        credential = login_tokens.issue_login_token(self.store, self.alice.id, 600)
        self.assertTrue(self.new_client().post("/api/login", json={"credential": credential}).json()["two_factor"])

    def test_disabling_the_account_ends_a_sign_in_in_progress(self) -> None:
        alice = self.sign_in_with_link(self.alice.id)
        secret, _ = self.enrol(alice)
        challenge = self.new_challenge()
        credentials.set_user_disabled(self.store, self.alice.id, True)
        self.assertEqual(self.finish(challenge, code_for(secret, 1)).json(), {"error": "challenge_invalid"})

    def test_turning_two_factor_on_ends_other_sessions(self) -> None:
        """S15: an attacker's session stayed signed in after the victim
        enrolled. The session that turned it on stays."""
        attacker = self.sign_in_with_link(self.alice.id)
        victim = self.sign_in_with_link(self.alice.id)
        self.enrol(victim)
        self.assertEqual(attacker.get("/api/me").status_code, 401)
        self.assertEqual(victim.get("/api/me").status_code, 200)

    def test_resetting_two_factor_ends_every_session(self) -> None:
        """S15: an admin resetting someone's two-factor ends every session
        that account holds."""
        alice = self.sign_in_with_link(self.alice.id)
        self.enrol(alice)
        owner = self.sign_in_with_link(self.owner.id)
        path = f"/api/admin/users/{self.alice.id}/reset-two-factor"
        self.assertEqual(owner.post(path, json={"csrf_token": self.csrf(owner)}).status_code, 200)
        self.assertEqual(alice.get("/api/me").status_code, 401)

    def test_reset_rules(self) -> None:
        second_admin = users.create_user(self.store, "Second", users.ROLE_ADMIN)
        admin_client = self.sign_in_with_link(second_admin.id)
        owner_client = self.sign_in_with_link(self.owner.id)
        alice = self.sign_in_with_link(self.alice.id)
        self.enrol(alice)
        self.enrol(owner_client)
        self.enrol(admin_client)

        def reset(client: TestClient, user_id: int) -> int:
            path = f"/api/admin/users/{user_id}/reset-two-factor"
            return client.post(path, json={"csrf_token": self.csrf(client)}).status_code

        self.assertEqual(reset(admin_client, self.owner.id), 403)
        self.assertEqual(reset(admin_client, second_admin.id), 400)
        self.assertEqual(reset(owner_client, self.owner.id), 400)
        self.assertEqual(reset(admin_client, self.alice.id), 200)
        self.assertEqual(reset(owner_client, second_admin.id), 200)
        self.assertFalse(two_factor.is_on(users.get_user(self.store, self.alice.id)))
        # The CLI may do what the web may not.
        self.assertTrue(credentials.reset_two_factor(self.store, self.owner.id, None))
        self.assertFalse(two_factor.is_on(users.get_user(self.store, self.owner.id)))


def login_rules(cfg: object) -> object:
    from app.routes.auth import sign_in_rules

    return sign_in_rules(cfg)
