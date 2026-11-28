"""Request boundary for account isolation, throttling and browser security."""

import os
import re
from urllib.parse import urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, RedirectResponse

from plantia import accounts
from plantia.config import MAX_IMAGE_SIZE_BYTES
from plantia.i18n import catalog, locale_for

COOKIE = "planet_session"
PUBLIC_PAGES = {"/", "/conta/entrar", "/conta/cadastro", "/conta/recuperar",
                "/conta/redefinir", "/conta/verificar", "/conta/reenviar", "/privacidade", "/idioma", "/health"}
AUTH_API = {"/api/auth/login", "/api/auth/register", "/api/auth/recover", "/api/auth/reset",
            "/api/auth/verify", "/api/auth/resend-verification"}
UPLOAD_ROUTES = {"/identificar", "/api/plantas/identificar"}


def secure_cookie():
    return os.getenv("PLANET_INSECURE_LOCAL_HTTP") != "1"


async def enforce_security(request, call_next):
    path = request.url.path
    method = request.method
    web = not path.startswith(("/api/", "/uploads/"))
    request.state.account_id = None
    if path.startswith("/static/") or path in {"/health", "/sw.js"} or (path in {"/api/stripe/webhook", "/api/stripe/webhook/live"} and method == "POST"):
        return await call_next(request)
    if path in {"/salir", "/configuracion", "/docs", "/redoc", "/openapi.json"}:
        return JSONResponse({"detail": catalog(locale_for(request)).get("Not found", "Not found")}, 404)

    authorization = request.headers.get("authorization", "")
    if authorization:
        token = authorization[7:] if authorization.startswith("Bearer ") else None
    else:
        token = request.cookies.get(COOKIE)
    request.state.token = token
    ip = request.client.host if request.client else "unknown"
    if not await run_in_threadpool(accounts.allow_request, f"ip:{ip}", 300, 60):
        return _reject(request, "Too many requests", 429)

    if method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if request.headers.get("sec-fetch-site") == "cross-site":
            return _reject(request, "Request blocked", 403)
        expected = os.getenv("PLANET_PUBLIC_ORIGIN", f"{request.url.scheme}://{request.url.netloc}").rstrip("/")
        if origin and origin != expected:
            return _reject(request, "Request blocked", 403)
        if request.cookies.get(COOKIE) and not authorization and not origin:
            referer = urlsplit(request.headers.get("referer", ""))
            if f"{referer.scheme}://{referer.netloc}" != expected:
                return _reject(request, "Request blocked", 403)
        health_upload = re.fullmatch(r"/(?:api/)?plantas/[0-9]+/saude/(?:avaliar|acompanhar)", path)
        cap = MAX_IMAGE_SIZE_BYTES + 64 * 1024 if path in UPLOAD_ROUTES else 64 * 1024
        if health_upload:
            cap += 2 * 1024 * 1024
        length = request.headers.get("content-length", "")
        if (length or request.headers.get("transfer-encoding") or path in UPLOAD_ROUTES or health_upload) and (not length.isdecimal() or len(length) > 12):
            return _reject(request, "Content-Length required", 411)
        if length and int(length) > cap:
            return _reject(request, "File or request too large", 413)

    request.state.account_id = await run_in_threadpool(accounts.account_for, token) if token else None
    if path not in (PUBLIC_PAGES | AUTH_API) and not request.state.account_id:
        if web and method == "GET":
            return RedirectResponse("/conta/entrar", 303)
        return _reject(request, "Sign in to continue", 401)

    if (request.state.account_id and accounts.verification_required()
            and path not in PUBLIC_PAGES | AUTH_API | {"/conta/sair", "/api/auth/logout", "/privacidade/excluir", "/api/auth/delete"}
            and not await run_in_threadpool(accounts.verified, request.state.account_id)):
        if web and method == "GET":
            return RedirectResponse("/conta/verificar", 303)
        return _reject(request, "privacy.required", 403)

    if method == "POST" and (path in AUTH_API or path.startswith("/conta/") and path != "/conta/sair"):
        if not await run_in_threadpool(accounts.allow_request, "auth:global", 120, 60):
            return _reject(request, "Too many requests", 429)
        if not await run_in_threadpool(accounts.allow_request, f"auth:{ip}", 12, 60):
            return _reject(request, "Too many requests", 429)
    if path in UPLOAD_ROUTES and method == "POST":
        if not await run_in_threadpool(accounts.allow_request, f"ai:{request.state.account_id}", 15, 3600):
            return _reject(request, "Too many requests", 429)
        if not await run_in_threadpool(accounts.allow_request, "ai:global", 120, 3600):
            return _reject(request, "Too many requests", 429)

    response = await call_next(request)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    return response


def _reject(request, key, status):
    if request.url.path.startswith(("/api/", "/uploads/")):
        return JSONResponse({"detail": catalog(locale_for(request)).get(key, key)}, status,
                            headers={"Cache-Control": "private, no-store"})
    from plantia.api.routes import templates
    return templates.TemplateResponse(request, "error.html", {"message_key": key}, status_code=status, headers={"Cache-Control": "private, no-store"})
