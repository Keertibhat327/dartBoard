"""Exercise authentication and developer authorization with isolated local accounts."""

import base64
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from api.accounts import password_hash, token_hash, verify_password
from api.server import COOKIE, create_app
from forecast.config import canonical_bytes, read_json
from labeling.schema import Dataset

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "Synthetic test passphrase only!"
HEADERS = {"X-Seer-Request": "1", "Origin": "http://testserver"}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Each test owns its own database and static directory, never real accounts."""
    (tmp_path / "configs").mkdir()
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("Synthetic UI test", encoding="utf-8")
    settings = read_json(ROOT / "configs" / "local_app.json")
    settings["auth_requests_per_minute"] = 100
    (tmp_path / "configs" / "local_app.json").write_bytes(canonical_bytes(settings))
    return TestClient(create_app(tmp_path), headers=HEADERS)


def register(client: TestClient) -> dict:
    response = client.post(
        "/api/register",
        json={
            "name": "Synthetic Student",
            "email": "student@example.test",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200
    return response.json()["user"]


def test_hashes_have_salts_and_do_not_store_password() -> None:
    first, second = password_hash(PASSWORD), password_hash(PASSWORD)
    assert first != second
    assert PASSWORD not in first
    assert verify_password(PASSWORD, first)
    assert not verify_password("wrong", first)


def test_registration_cookie_and_restart_persistence(client: TestClient) -> None:
    profile = register(client)
    assert profile["role"] == "user"
    assert set(profile) == {"id", "email", "name", "role", "created_at"}
    assert client.get("/api/me").json()["user"]["id"] == profile["id"]
    from api.accounts import Accounts

    fresh = Accounts(client.app.state.accounts.path)
    token = client.cookies.get(COOKIE)
    assert fresh.user(token)["id"] == profile["id"]
    with fresh.connection() as db:
        session = db.execute("SELECT token_hash FROM sessions").fetchone()[0]
        stored = db.execute("SELECT password_hash FROM users").fetchone()[0]
    assert session == token_hash(token) and session != token
    assert stored != PASSWORD


def test_cookie_flags(client: TestClient) -> None:
    response = client.post(
        "/api/register",
        json={
            "name": "Synthetic Student",
            "email": "flags@example.test",
            "password": PASSWORD,
        },
    )
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert response.headers["cache-control"] == "no-store"


def test_login_logout_and_bad_password(client: TestClient) -> None:
    register(client)
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/me").json()["user"] is None
    assert client.get("/api/subjects").status_code == 401
    assert (
        client.post(
            "/api/login", json={"email": "student@example.test", "password": "wrong"}
        ).status_code
        == 401
    )
    response = client.post(
        "/api/login", json={"email": "STUDENT@example.test", "password": PASSWORD}
    )
    assert response.status_code == 200


def test_signup_cannot_choose_developer_role(client: TestClient) -> None:
    response = client.post(
        "/api/register",
        json={
            "name": "Synthetic Student",
            "email": "student@example.test",
            "password": PASSWORD,
            "role": "developer",
        },
    )
    assert response.status_code == 400
    register(client)
    assert client.get("/api/developer").status_code == 403
    assert client.post("/api/developer/datasets", json={}).status_code == 403
    assert (
        client.patch(
            "/api/profile", json={"name": "Synthetic Dev", "role": "developer"}
        ).status_code
        == 400
    )
    client.app.state.accounts.grant_developer("student@example.test")
    assert client.get("/api/developer").status_code == 200


def test_profile_edit_does_not_change_other_account(client: TestClient) -> None:
    profile = register(client)
    response = client.patch("/api/profile", json={"name": "Synthetic Renamed"})
    assert response.json()["user"]["name"] == "Synthetic Renamed"
    assert response.json()["user"]["id"] == profile["id"]
    assert client.patch("/api/profile", json={"name": ""}).status_code == 400


def test_password_change_revokes_all_sessions(client: TestClient) -> None:
    profile = register(client)
    accounts = client.app.state.accounts
    second = accounts.create_session(profile["id"])
    assert (
        client.post(
            "/api/password", json={"current": "wrong", "replacement": "New synthetic password!"}
        ).status_code
        == 400
    )
    response = client.post(
        "/api/password", json={"current": PASSWORD, "replacement": "New synthetic password!"}
    )
    assert response.status_code == 200
    assert accounts.user(second) is None
    assert client.get("/api/me").json()["user"] is None
    assert accounts.login("student@example.test", PASSWORD) is None
    assert accounts.login("student@example.test", "New synthetic password!") is not None


def test_cross_origin_and_missing_request_header_rejected(client: TestClient) -> None:
    assert (
        client.post("/api/logout", headers={"Origin": "https://elsewhere.test"}).status_code == 403
    )
    assert client.post("/api/logout", headers={"X-Seer-Request": ""}).status_code == 403
    assert client.get("/api/me", headers={"host": "elsewhere.test"}).status_code == 400


def test_rate_limit_and_request_size(client: TestClient) -> None:
    accounts = client.app.state.accounts
    assert accounts.allow_attempt("synthetic-key", 1)
    assert not accounts.allow_attempt("synthetic-key", 1)
    response = client.post("/api/login", json={"email": "x" * 20000})
    assert response.status_code == 413


def test_bmsit_exam_types_do_not_mix(client: TestClient, dataset: Dataset) -> None:
    register(client)
    client.app.state.accounts.grant_developer("student@example.test")
    for assessment in ("internal", "semester_end"):
        response = client.post(
            "/api/developer/datasets",
            json={
                "assessment_type": assessment,
                "dataset": dataset.to_dict(),
            },
        )
        assert response.status_code == 200
        assert response.json()["snapshots_added"] == len(dataset.subjects)
    history = client.get("/api/developer").json()["subjects"]
    assert len(history) == len(dataset.subjects) * 2
    assert {s["latest"]["assessment_type"] for s in history} == {"internal", "semester_end"}
    assert all(s["latest"]["institution"] == "BMSIT" for s in history)
    assert all(s["latest"]["metrics"] is None for s in history)
    assert all(s["latest"]["is_synthetic"] for s in history)


def test_revision_counts_duplicates_and_no_fake_metrics(
    client: TestClient, dataset: Dataset
) -> None:
    register(client)
    client.app.state.accounts.grant_developer("student@example.test")

    def upload(value: Dataset) -> dict:
        response = client.post(
            "/api/developer/datasets",
            json={
                "assessment_type": "internal",
                "dataset": value.to_dict(),
            },
        )
        assert response.status_code == 200
        return response.json()

    assert upload(dataset)["snapshots_added"] == len(dataset.subjects)
    assert upload(dataset)["snapshots_added"] == 0
    paper = replace(dataset.papers[0], id="SYN-EXTRA", year=2030)
    old_question = dataset.questions[0]
    question = replace(old_question, id="SYN-EXTRA-Q", paper_id=paper.id)
    label = replace(dataset.labels[0], question_id=question.id)
    revised = replace(
        dataset,
        papers=dataset.papers + (paper,),
        questions=dataset.questions + (question,),
        labels=dataset.labels + (label,),
    )
    upload(revised)
    subjects = client.get("/api/developer").json()["subjects"]
    tracked = next(s for s in subjects if s["latest"]["subject_id"] == paper.subject_id)
    assert len(tracked["history"]) == 2
    assert tracked["latest"]["added_papers"] == 1
    assert tracked["latest"]["removed_papers"] == 0
    assert tracked["latest"]["paper_count"] == tracked["history"][0]["paper_count"] + 1
    assert tracked["latest"]["metrics"] is None
    assert tracked["latest"]["evaluation_status"] == "Not evaluated"
    assert "text" not in str(client.get("/api/subjects").json())


def test_invalid_dataset_and_unscoped_assessment_rejected(client: TestClient) -> None:
    register(client)
    client.app.state.accounts.grant_developer("student@example.test")
    assert client.post("/api/developer/datasets", json={"dataset": {}}).status_code == 400
    assert (
        client.post(
            "/api/developer/datasets", json={"assessment_type": "internal", "dataset": {}}
        ).status_code
        == 400
    )


def test_separate_login_portals_enforce_roles(client: TestClient) -> None:
    register(client)
    client.post("/api/logout")
    credentials = {"email": "student@example.test", "password": PASSWORD}
    assert client.post("/api/login/developer", json=credentials).status_code == 403
    assert client.get("/api/me").json()["user"] is None
    assert client.post("/api/login/user", json=credentials).status_code == 200
    client.app.state.accounts.grant_developer(credentials["email"])
    client.post("/api/logout")
    assert client.post("/api/login/user", json=credentials).status_code == 403
    assert client.post("/api/login/developer", json=credentials).status_code == 200
    assert client.post("/api/login/arbitrary", json=credentials).status_code == 404


def test_sources_history_institutions_and_user_paper_access(
    client: TestClient, dataset: Dataset
) -> None:
    register(client)
    client.app.state.accounts.grant_developer("student@example.test")
    pdf = b"%PDF-1.4\n% SYNTHETIC source-byte test; not a real paper.\n%%EOF"
    paper = dataset.papers[0]
    for institution in ("BMSIT", "VTU"):
        payload = {
            "institution": institution,
            "assessment_type": "internal",
            "dataset": dataset.to_dict(),
            "filename": "SYNTHETIC-fixture.json",
            "sources": [
                {
                    "name": "SYNTHETIC-paper.pdf",
                    "paper_id": paper.id,
                    "content_base64": base64.b64encode(pdf).decode(),
                }
            ],
        }
        assert client.post("/api/developer/datasets", json=payload).status_code == 200
    assert client.post("/api/developer/datasets", json=payload).json()["snapshots_added"] == 0
    developer = client.get("/api/developer").json()
    assert len(developer["uploads"]) == 3
    assert len(developer["subjects"]) == len(dataset.subjects) * 2
    source = developer["uploads"][0]["payload"]["sources"][0]
    client.post("/api/logout")
    assert client.get(f"/api/files/{source['hash']}").status_code == 401
    client.post(
        "/api/register",
        json={"name": "Synthetic Reader", "email": "reader@example.test", "password": PASSWORD},
    )
    assert client.get("/api/developer").status_code == 403
    assert client.post("/api/developer/predictions", json={}).status_code == 403
    assert client.get("/api/developer/uploads/1").status_code == 403
    assert client.get(f"/api/files/{source['hash']}").content == pdf
    assert "attachment" in client.get(f"/api/files/{source['hash']}").headers["content-disposition"]
    collections = client.get("/api/subjects").json()["subjects"]
    assert {s["institution"] for s in collections} == {"VTU", "BMSIT"}
    for subject in collections:
        response = client.get(f"/api/papers/{subject['id']}/{subject['paper_ids'][0]}")
        assert response.status_code == 200
        assert response.json()["questions"]
        assert response.json()["is_synthetic"]


def test_frozen_prediction_scores_once_and_requires_confirmation(
    client: TestClient, dataset: Dataset
) -> None:
    register(client)
    client.app.state.accounts.grant_developer("student@example.test")

    def upload(value: Dataset, institution: str = "BMSIT", ready: bool = True) -> None:
        response = client.post(
            "/api/developer/datasets",
            json={
                "dataset": value.to_dict(),
                "institution": institution,
                "assessment_type": "internal",
                "evaluation_ready": ready,
            },
        )
        assert response.status_code == 200, response.text

    upload(dataset)
    collection = client.get("/api/developer").json()["subjects"][0]
    target = {
        "series": collection["id"],
        "paper_id": "SYN-TARGET",
        "year": 2030,
        "sitting": "SYN-IA1",
        "k": 1,
    }
    assert client.post("/api/developer/predictions", json=target).status_code == 200
    assert client.post("/api/developer/predictions", json=target).status_code == 400
    frozen = client.get("/api/developer").json()["predictions"][0]
    topic = next(t for t in dataset.topics if t.id == frozen["payload"]["topics"][0]["id"])
    paper = replace(
        next(p for p in dataset.papers if p.subject_id == topic.subject_id),
        id=target["paper_id"],
        year=2030,
        sitting=target["sitting"],
    )
    question = replace(
        dataset.questions[0], id="SYN-TARGET-Q", paper_id=paper.id, module=topic.module, marks=7
    )
    label = replace(dataset.labels[0], question_id=question.id, topic_id=topic.id)
    revised = replace(
        dataset,
        papers=dataset.papers + (paper,),
        questions=dataset.questions + (question,),
        labels=dataset.labels + (label,),
    )
    upload(revised, "VTU")
    assert client.get("/api/developer").json()["predictions"][0]["result"] is None
    upload(revised, ready=False)
    assert client.get("/api/developer").json()["predictions"][0]["result"] is None
    upload(revised)
    scored = client.get("/api/developer").json()["predictions"][0]
    assert scored["payload"] == frozen["payload"]
    assert scored["result"]["metrics"] == {
        "marks_coverage": 1,
        "precision": 1,
        "recall": 1,
        "covered_marks": 7,
        "total_listed_marks": 7,
    }
    changed = replace(
        revised,
        questions=tuple(
            replace(q, marks=11) if q.id == question.id else q for q in revised.questions
        ),
    )
    upload(changed)
    assert client.get("/api/developer").json()["predictions"][0] == scored
    target["paper_id"] = dataset.papers[0].id
    assert client.post("/api/developer/predictions", json=target).status_code == 400


def test_bad_sources_and_unknown_institution_are_rejected(
    client: TestClient, dataset: Dataset
) -> None:
    register(client)
    client.app.state.accounts.grant_developer("student@example.test")
    payload = {
        "dataset": dataset.to_dict(),
        "assessment_type": "internal",
        "institution": "Unknown",
    }
    assert client.post("/api/developer/datasets", json=payload).status_code == 400
    payload["institution"] = "VTU"
    for sources in [
        {},
        [{"name": "../escape.pdf", "paper_id": dataset.papers[0].id}],
        [
            {
                "name": "fake.pdf",
                "paper_id": dataset.papers[0].id,
                "content_base64": base64.b64encode(b"Not a PDF").decode(),
            }
        ],
    ]:
        payload["sources"] = sources
        assert client.post("/api/developer/datasets", json=payload).status_code == 400
    assert client.get("/api/developer").json()["uploads"] == []
