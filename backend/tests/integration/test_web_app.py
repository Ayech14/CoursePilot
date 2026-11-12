"""Production serves the built web app from the API, on one origin, with a strict page policy."""

import base64
import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.web import web_policy
from app.db.session import get_db
from app.main import create_app
from tests.integration.helpers import new_user

THEME_SCRIPT = (
    "\n      (function () { document.documentElement.dataset.theme = 'light'; })();\n    "
)
INDEX = f"""<!doctype html>
<html><head><script>{THEME_SCRIPT}</script>
<script type="module" crossorigin src="/assets/index-abc123.js"></script></head>
<body><div id="root"></div></body></html>"""


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log('app');\n" * 200)
    (tmp_path / "index.html").write_text(INDEX)
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path.parent / "secret.txt").write_text("outside")
    return tmp_path


@pytest.fixture
def web(db: Session, dist: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("STATIC_DIR", str(dist))
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def test_policy_allows_only_the_theme_script_by_hash() -> None:
    digest = base64.b64encode(hashlib.sha256(THEME_SCRIPT.encode()).digest()).decode()
    policy = web_policy(INDEX)
    assert f"script-src 'self' 'sha256-{digest}';" in policy
    assert "'unsafe-inline'" not in policy.split("script-src")[1].split(";")[0]
    assert "frame-ancestors 'none'" in policy
    assert "connect-src 'self'" in policy
    assert "font-src 'self' data:;" in policy  # The calendar's icon font.


@pytest.mark.parametrize("path", ["/", "/dashboard", "/courses/0190-abc", "/tasks?x=1"])
def test_every_app_route_is_the_app_page(web: TestClient, path: str) -> None:
    response = web.get(path)
    assert response.status_code == 200
    assert '<div id="root">' in response.text
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-security-policy"] == web_policy(INDEX)
    assert response.headers["x-frame-options"] == "DENY"


def test_pages_answer_head_requests_from_uptime_checkers(web: TestClient) -> None:
    assert web.head("/dashboard").status_code == 200


def test_assets_are_cached_for_good(web: TestClient) -> None:
    response = web.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert web.get("/assets/missing.js").status_code == 404


def test_assets_are_compressed_but_api_answers_are_not(web: TestClient) -> None:
    gzip = {"accept-encoding": "gzip"}
    assert web.get("/assets/index-abc123.js", headers=gzip).headers["content-encoding"] == "gzip"
    headers = new_user(web, "UTC")
    me = web.get("/api/v1/users/me", headers={**headers, **gzip})
    assert "content-encoding" not in me.headers


def test_top_level_files_are_served_but_nothing_outside(web: TestClient) -> None:
    assert web.get("/favicon.svg").text == "<svg/>"
    assert "outside" not in web.get("/../secret.txt").text
    assert "outside" not in web.get("/%2e%2e/secret.txt").text


def test_the_api_keeps_its_own_answers_and_policy(web: TestClient) -> None:
    missing = web.get("/api/v1/nothing-here")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert (
        missing.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    )
    assert web.get("/health").json()["status"] == "ok"
    headers = new_user(web, "UTC")
    me = web.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200
    assert me.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in me.headers["content-security-policy"]


def test_a_missing_build_fails_at_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="no index.html"):
        create_app()
    get_settings.cache_clear()


def test_without_a_build_there_are_no_pages(client: TestClient) -> None:
    assert client.get("/dashboard").status_code == 404


def test_rate_limits_use_the_platform_header_when_configured(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLIENT_IP_HEADER", "true-client-ip")
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    body = {"email": "nobody@example.com", "password": "wrong-password-123"}
    with TestClient(app) as client:
        for _ in range(5):
            client.post("/api/v1/auth/login", json=body, headers={"true-client-ip": "1.1.1.1"})
        blocked = client.post(
            "/api/v1/auth/login", json=body, headers={"true-client-ip": "1.1.1.1"}
        )
        other = client.post("/api/v1/auth/login", json=body, headers={"true-client-ip": "2.2.2.2"})
        # X-Forwarded-For is written by the visitor, so it never changes who they are.
        spoofed = client.post(
            "/api/v1/auth/login",
            json=body,
            headers={"true-client-ip": "1.1.1.1", "x-forwarded-for": "3.3.3.3"},
        )
    get_settings.cache_clear()
    assert blocked.status_code == 429
    assert other.status_code == 401
    assert spoofed.status_code == 429
