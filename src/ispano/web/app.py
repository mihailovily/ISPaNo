"""FastAPI application exposing protected export and report workflows."""

from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

import bcrypt
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from ..cli import _parse_since
from ..settings import AppSettings
from ..services import create_json_export, create_ticket_report
from .jobs import JobManager, WebJob

WEB_ROOT = Path(__file__).resolve().parents[3] / "web"


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Требуется вход в веб-интерфейс.")


def _require_user(request: Request) -> None:
    if not request.session.get("username"):
        raise _unauthorized()


def _login_redirect() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)


def _require_csrf(request: Request) -> None:
    _require_user(request)
    if not secrets.compare_digest(
        request.headers.get("X-CSRF-Token", ""), request.session.get("csrf", "")
    ):
        raise HTTPException(status_code=403, detail="Некорректный CSRF-токен.")


def _job_or_404(manager: JobManager, job_id: str) -> WebJob:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задание не найдено.")
    return job


def create_app(settings: AppSettings) -> FastAPI:
    """Create a web app. Job state intentionally lasts only for this process."""
    web = settings.require_web()
    app = FastAPI(title="ISPaNo")
    app.add_middleware(
        SessionMiddleware,
        secret_key=web.session_secret,
        same_site="lax",
        https_only=False,
    )
    manager = JobManager()
    app.state.jobs = manager

    @app.get("/login")
    async def login_page() -> FileResponse:
        return FileResponse(WEB_ROOT / "login.html")

    @app.post("/api/login")
    async def login(request: Request) -> JSONResponse:
        body: dict[str, Any] = await request.json()
        username = body.get("username", "")
        password = body.get("password", "")
        valid = (
            isinstance(username, str)
            and isinstance(password, str)
            and secrets.compare_digest(username, web.username)
            and bcrypt.checkpw(password.encode(), web.password_hash.encode())
        )
        if not valid:
            raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль.")
        request.session.clear()
        request.session.update({"username": web.username, "csrf": secrets.token_urlsafe(32)})
        return JSONResponse({"ok": True})

    @app.post("/api/logout")
    async def logout(request: Request) -> JSONResponse:
        _require_csrf(request)
        request.session.clear()
        return JSONResponse({"ok": True})

    @app.get("/api/session")
    async def session(request: Request) -> dict[str, object]:
        _require_user(request)
        return {
            "username": request.session["username"],
            "csrf": request.session["csrf"],
            "ai_enabled": settings.ticket_summary.enabled,
        }

    @app.get("/")
    async def index(request: Request) -> Response:
        if not request.session.get("username"):
            return _login_redirect()
        return FileResponse(WEB_ROOT / "index.html")

    @app.get("/viewer")
    async def viewer(request: Request) -> Response:
        if not request.session.get("username"):
            return _login_redirect()
        return FileResponse(WEB_ROOT / "viewer.html")

    @app.get("/assets/{filename}")
    async def asset(request: Request, filename: str) -> FileResponse:
        _require_user(request)
        if filename not in {"app.js", "viewer.js"}:
            raise HTTPException(status_code=404, detail="Ресурс не найден.")
        return FileResponse(WEB_ROOT / filename, media_type="text/javascript")

    @app.post("/api/jobs/json")
    async def start_json_job(request: Request) -> dict[str, object]:
        _require_csrf(request)
        body: dict[str, Any] = await request.json()
        raw_since = body.get("since", "")
        if not isinstance(raw_since, str) or not raw_since.strip():
            raise HTTPException(status_code=422, detail="Укажите дату отсечения.")
        try:
            cutoff = _parse_since(raw_since.strip())
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        def run(report: Any) -> Path:
            _, path = create_json_export(settings, cutoff, report)
            return Path(path)

        return manager.submit("json", run).public()

    @app.post("/api/jobs/report")
    async def start_report_job(request: Request) -> dict[str, object]:
        _require_csrf(request)
        body: dict[str, Any] = await request.json()
        ticket_id = body.get("ticket_id")
        use_ai = body.get("use_ai", False)
        if isinstance(ticket_id, bool) or not isinstance(ticket_id, int) or ticket_id <= 0:
            raise HTTPException(status_code=422, detail="Номер тикета должен быть положительным целым числом.")
        if not isinstance(use_ai, bool):
            raise HTTPException(status_code=422, detail="Параметр use_ai должен быть логическим.")
        if use_ai and not settings.ticket_summary.enabled:
            raise HTTPException(status_code=422, detail="ИИ-суммаризация не настроена.")

        def run(report: Any) -> Path:
            path, _ = create_ticket_report(settings, ticket_id, use_ai=use_ai, report=report)
            return Path(path)

        return manager.submit("report", run).public()

    @app.get("/api/jobs/{job_id}")
    async def job_status(request: Request, job_id: str) -> dict[str, object]:
        _require_user(request)
        return _job_or_404(manager, job_id).public()

    @app.get("/api/jobs/{job_id}/download")
    async def download(request: Request, job_id: str) -> FileResponse:
        _require_user(request)
        job = _job_or_404(manager, job_id)
        if job.result_path is None or not job.result_path.is_file():
            raise HTTPException(status_code=404, detail="Результат задания пока недоступен.")
        return FileResponse(job.result_path, filename=job.result_path.name)

    return app
