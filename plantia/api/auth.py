"""Account endpoints shared by the web and Android clients."""

import logging
import os

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

from plantia import accounts
from plantia.i18n import catalog, locale_for
from plantia.security import COOKIE, secure_cookie

router = APIRouter()
PAGES = {
    "entrar": "Sign in",
    "cadastro": "Create account",
    "recuperar": "Recover password",
    "redefinir": "Reset password",
}


def render(request, action, message=None, status=200):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": catalog(locale_for(request)).get(message, message)}, status)
    from plantia.api.routes import templates
    return templates.TemplateResponse(request, "account.html",
        {"action": action, "heading": PAGES[action], "message_key": message}, status_code=status)


@router.get("/conta/{action}")
def account_page(request: Request, action: str):
    if action not in PAGES:
        return RedirectResponse("/conta/entrar", 303)
    return render(request, action)


def normalized(email):
    if len(email) > 254:
        return None
    try:
        return validate_email(email.strip(), check_deliverability=False).normalized.casefold()
    except EmailNotValidError:
        return None


@router.post("/conta/cadastro")
@router.post("/api/auth/register")
def register(request: Request, email: str = Form(...), password: str = Form(...)):
    email = normalized(email)
    if not email or not 12 <= len(password) <= 128:
        return render(request, "cadastro", "Enter a valid email and a password of 12–128 characters", 400)
    accounts.register(email, password)
    if request.url.path.startswith("/api/"):
        return render(request, "entrar", "You can now try signing in", 202)
    return render(request, "entrar", "You can now try signing in")


@router.post("/conta/entrar")
@router.post("/api/auth/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    email = normalized(email)
    if email and not accounts.allow_request(f"login:{accounts.digest(email)}", 8, 60):
        return render(request, "entrar", "Too many requests", 429)
    token = accounts.login(email, password) if email and len(password) <= 128 else None
    if not token:
        return render(request, "entrar", "Invalid email or password", 401)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"access_token": token, "token_type": "bearer", "account_id": accounts.account_for(token)})
    accounts.logout(request.state.token)
    response = RedirectResponse("/", 303)
    response.set_cookie(COOKIE, token, max_age=accounts.SESSION_AGE,
                        httponly=True, secure=secure_cookie(), samesite="lax")
    return response


@router.post("/conta/sair")
@router.post("/api/auth/logout")
def logout(request: Request):
    accounts.logout(request.state.token)
    response = (JSONResponse({"ok": True}) if request.url.path.startswith("/api/")
                else RedirectResponse("/", 303))
    response.delete_cookie(COOKIE)
    return response


@router.post("/conta/recuperar")
@router.post("/api/auth/recover")
def recover(request: Request, email: str = Form(...)):
    if not all(os.getenv(k) for k in ("PLANET_PUBLIC_ORIGIN", "PLANET_SMTP_HOST", "PLANET_SMTP_FROM")):
        return render(request, "recuperar", "Password recovery is unavailable", 503)
    email = normalized(email)
    if email and accounts.allow_request(f"recover:{accounts.digest(email)}", 2, 60):
        token = accounts.issue_recovery(email)
        if token:
            from starlette.background import BackgroundTask

            locale = locale_for(request)

            def deliver():
                try:
                    accounts.send_recovery(email, token, locale)
                except (OSError, ValueError, KeyError):
                    logging.getLogger(__name__).warning("PLANET-IA recovery email delivery failed")

            response = render(request, "recuperar", "If the account exists, a recovery code will be sent")
            response.background = BackgroundTask(deliver)
            return response
    return render(request, "recuperar", "If the account exists, a recovery code will be sent")


@router.post("/conta/redefinir")
@router.post("/api/auth/reset")
def reset(request: Request, token: str = Form(...), password: str = Form(...)):
    if not 12 <= len(password) <= 128 or not accounts.reset_password(token.strip(), password):
        return render(request, "redefinir", "Invalid or expired code, or password length outside 12–128 characters", 400)
    return render(request, "entrar", "Password updated. Sign in again")
