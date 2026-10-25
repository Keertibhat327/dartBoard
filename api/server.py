"""Local-only account server; web assets are public, private APIs require sessions."""

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api.accounts import Accounts
from api.evidence import prediction_history, save_prediction, upload_history
from api.tracking import record_dataset, subject_history
from forecast.config import canonical_bytes, read_json
from labeling.schema import Dataset

ROOT = Path(__file__).resolve().parents[1]
COOKIE = "seer_session"


def load_settings(root: Path) -> dict[str, Any]:
    """Refuse external binds or database paths: this application is not a hosted release."""
    settings = read_json(root / "configs" / "local_app.json")
    if settings["forecast"]["method"] != "global_frequency_v1":
        raise ValueError("Only the configured global_frequency_v1 method is implemented.")
    if type(settings["forecast"]["seed"]) is not int or settings["forecast"]["seed"] < 0:
        raise ValueError("Forecast seed must be a nonnegative integer.")
    if settings["host"] != "127.0.0.1":
        raise ValueError("The account preview must bind to 127.0.0.1.")
    database = (root / settings["database"]).resolve()
    if not database.is_relative_to((root / "data").resolve()):
        raise ValueError("Account database must live under data/.")
    return settings


def create_app(root: Path = ROOT) -> FastAPI:
    """Build an isolated app so tests never share the user's real account database."""
    settings = load_settings(root)
    accounts = Accounts(root / settings["database"], settings["session_hours"])
    app = FastAPI(
        title="dartboard local workspace", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.accounts = accounts
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.middleware("http")
    async def protect(request: Request, call_next: Any) -> Any:
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            host = request.headers.get("host")
            if request.headers.get("x-seer-request") != "1" or (
                origin is not None and urlsplit(origin).netloc != host
            ):
                return JSONResponse({"detail": "Request origin rejected."}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' "
            "https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'"
        )
        return response

    async def body(request: Request, limit: int = 16384) -> dict[str, Any]:
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            raise HTTPException(415, "Send JSON data.")
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > limit:
                raise HTTPException(413, "Request is too large.")
        try:
            result = json.loads(content)
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(400, "Invalid JSON.") from exc
        if not isinstance(result, dict):
            raise HTTPException(400, "Expected an object.")
        return result

    def user(request: Request, developer: bool = False) -> dict[str, Any]:
        result = accounts.user(request.cookies.get(COOKIE, ""))
        if result is None:
            raise HTTPException(401, "Sign in to continue.")
        if developer and result["role"] != "developer":
            raise HTTPException(403, "Developer access is required.")
        return result

    def rate_limit(request: Request) -> None:
        client = request.client.host if request.client else "local"
        if not accounts.allow_attempt(client, settings["auth_requests_per_minute"]):
            raise HTTPException(429, "Too many attempts. Wait a minute and try again.")

    def session_response(token: str) -> JSONResponse:
        response = JSONResponse({"user": accounts.user(token)})
        response.set_cookie(
            COOKIE,
            token,
            httponly=True,
            samesite="strict",
            secure=False,
            max_age=accounts.session_seconds,
            path="/",
        )
        return response

    @app.exception_handler(ValueError)
    async def invalid_input(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/api/me")
    def me(request: Request) -> dict[str, Any]:
        return {"user": accounts.user(request.cookies.get(COOKIE, ""))}

    @app.get("/api/workspace")
    def workspace() -> dict[str, Any]:
        return {
            "institution": settings["institution"],
            "institutions": settings["institutions"],
            "forecast": settings["forecast"],
            "max_upload_bytes": settings["max_upload_bytes"],
            "max_dataset_bytes": settings["max_dataset_bytes"],
            "assessment_types": settings["assessment_types"],
        }

    @app.post("/api/register")
    async def register(request: Request) -> JSONResponse:
        rate_limit(request)
        values = await body(request)
        if set(values) != {"email", "name", "password"}:
            raise HTTPException(400, "Provide only name, email and password.")
        created = accounts.register(**values)
        return session_response(accounts.create_session(created["id"]))

    @app.post("/api/login")
    @app.post("/api/login/{portal}")
    async def login(request: Request, portal: str = "user") -> JSONResponse:
        rate_limit(request)
        values = await body(request)
        if portal not in ("user", "developer"):
            raise HTTPException(404, "Unknown sign-in portal.")
        token = accounts.login(values.get("email"), values.get("password"))
        if token is None:
            raise HTTPException(401, "Email or password is incorrect.")
        if accounts.user(token)["role"] != portal:
            accounts.logout(token)
            raise HTTPException(403, "Use the sign-in page for your account role.")
        return session_response(token)

    @app.post("/api/logout")
    async def logout(request: Request) -> JSONResponse:
        accounts.logout(request.cookies.get(COOKIE, ""))
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, path="/")
        return response

    @app.patch("/api/profile")
    async def profile(request: Request) -> dict[str, Any]:
        current = user(request)
        values = await body(request)
        if set(values) != {"name"}:
            raise HTTPException(400, "Only the display name can be changed here.")
        accounts.update_name(current["id"], values["name"])
        return {"user": user(request)}

    @app.post("/api/password")
    async def password(request: Request) -> JSONResponse:
        current = user(request)
        rate_limit(request)
        values = await body(request)
        if not accounts.change_password(
            current["id"], values.get("current"), values.get("replacement")
        ):
            raise HTTPException(400, "Current password is incorrect.")
        return await logout(request)

    @app.get("/api/subjects")
    def subjects(request: Request) -> dict[str, Any]:
        user(request)
        return {
            "subjects": [{"id": item["id"], **item["latest"]} for item in subject_history(accounts)]
        }

    @app.get("/api/developer")
    def developer(request: Request) -> dict[str, Any]:
        user(request, developer=True)
        return {
            "subjects": subject_history(accounts),
            "uploads": upload_history(accounts),
            "predictions": prediction_history(accounts),
        }

    @app.post("/api/developer/predictions")
    async def predict(request: Request) -> dict[str, Any]:
        user(request, developer=True)
        values = await body(request)
        return {"prediction_id": save_prediction(accounts, root, values, settings["forecast"])}

    @app.get("/api/papers/{series}/{paper_id}")
    def paper(request: Request, series: str, paper_id: str) -> dict[str, Any]:
        user(request)
        collection = next((s for s in subject_history(accounts) if s["id"] == series), None)
        if collection is None or paper_id not in collection["latest"]["paper_ids"]:
            raise HTTPException(404, "Paper not found.")
        latest = collection["latest"]
        dataset = Dataset.from_dict(
            read_json(root / "data" / "imports" / f"{latest['data_hash']}.json")
        )
        raw = dataset.to_dict()
        questions = [q for q in raw["questions"] if q["paper_id"] == paper_id]
        uploads = [
            u
            for u in upload_history(accounts)
            if u["institution"] == latest["institution"]
            and u["assessment_type"] == latest["assessment_type"]
            and u["data_hash"] in {h["data_hash"] for h in collection["history"]}
        ]
        sources = {
            s["hash"]: s
            for u in uploads
            for s in u["payload"]["sources"]
            if s["paper_id"] == paper_id
        }
        return {
            "paper": next(p for p in raw["papers"] if p["id"] == paper_id),
            "questions": questions,
            "sources": list(sources.values()),
            "institution": latest["institution"],
            "subject": latest["name"],
            "is_synthetic": dataset.is_synthetic,
        }

    @app.get("/api/files/{digest}")
    def download(request: Request, digest: str) -> FileResponse:
        user(request)
        for upload in upload_history(accounts):
            for source in upload["payload"]["sources"]:
                if digest == source["hash"]:
                    return FileResponse(
                        root / "data" / "sources" / f"{digest}.pdf",
                        media_type="application/pdf",
                        filename=source["name"],
                    )
        raise HTTPException(404, "Source not found.")

    @app.get("/api/developer/uploads/{upload_id}")
    def download_dataset(request: Request, upload_id: int) -> FileResponse:
        user(request, developer=True)
        upload = next((u for u in upload_history(accounts) if u["id"] == upload_id), None)
        if upload is None:
            raise HTTPException(404, "Upload not found.")
        return FileResponse(
            root / "data" / "imports" / f"{upload['data_hash']}.json",
            media_type="application/json",
            filename="dataset.json",
        )

    @app.post("/api/developer/datasets")
    async def dataset(request: Request) -> dict[str, Any]:
        user(request, developer=True)
        values = await body(request, settings["max_upload_bytes"])
        if len(canonical_bytes(values.get("dataset"))) > settings["max_dataset_bytes"]:
            raise HTTPException(413, "Dataset JSON exceeds the configured limit.")
        institution = values.get("institution", settings["institution"])
        if institution not in settings["institutions"]:
            raise HTTPException(400, "Choose VTU or BMSIT.")
        assessment = values.get("assessment_type")
        if not isinstance(assessment, str) or assessment not in settings["assessment_types"]:
            raise HTTPException(400, "Choose an internal assessment or semester-end exam.")
        try:
            added = record_dataset(
                accounts,
                root,
                values.get("dataset"),
                institution,
                assessment,
                values.get("filename", "dataset.json"),
                values.get("sources", []),
                values.get("evaluation_ready", False),
            )
        except (TypeError, KeyError) as exc:
            raise HTTPException(400, "Dataset does not match the dartboard schema.") from exc
        return {"snapshots_added": added}

    app.mount("/", StaticFiles(directory=root / "web", html=True), name="web")
    return app


def main() -> None:
    """Use the configured loopback port for the local account-enabled preview."""
    import uvicorn

    settings = load_settings(ROOT)
    uvicorn.run(create_app(), host=settings["host"], port=settings["port"])


if __name__ == "__main__":
    main()
