"""Account endpoints shared by the web and Android clients."""

import logging
import os

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Form, HTTPException, Request
from starlette.background import BackgroundTask
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
    "verificar": "privacy.verify",
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
    created = accounts.register(email, password)
    if accounts.verification_required():
        response = render(request, "verificar", "privacy.sent", 202)
        return _verification_delivery(request, email, response) if created else response
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
    if accounts.verification_required() and not accounts.verified(accounts.account_for(token)):
        accounts.logout(token)
        return render(request, "verificar", "privacy.required", 403)
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
    if not accounts.email_delivery_configured():
        return render(request, "recuperar", "Password recovery is unavailable", 503)
    email = normalized(email)
    if email and accounts.allow_request(f"recover:{accounts.digest(email)}", 2, 60):
        token = accounts.issue_recovery(email)
        if token:
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


def _verification_delivery(request, email, response):
    if not accounts.email_delivery_configured():
        return render(request, "verificar", "privacy.unavailable", 503)
    if email and accounts.allow_request(f"verify:{accounts.digest(email)}", 2, 60):
        token = accounts.issue_verification(email)
        if token:
            locale = locale_for(request)

            def deliver():
                try:
                    accounts.send_verification(email, token, locale)
                except (OSError, ValueError, KeyError):
                    logging.getLogger(__name__).warning("PLANET-IA verification email delivery failed")

            response.background = BackgroundTask(deliver)
    return response


@router.post("/conta/reenviar")
@router.post("/api/auth/resend-verification")
def resend_verification(request: Request, email: str = Form(...)):
    return _verification_delivery(request, normalized(email), render(request, "verificar", "privacy.sent", 202))


@router.post("/conta/verificar")
@router.post("/api/auth/verify")
def verify(request: Request, token: str = Form(..., max_length=64), password: str = Form(..., max_length=128)):
    if not accounts.verify_email(token.strip(), password):
        return render(request, "verificar", "privacy.invalid", 400)
    return render(request, "entrar", "privacy.verified")


@router.get("/privacidade")
def privacy(request: Request):
    from plantia.api.routes import templates
    owner = request.state.account_id
    return templates.TemplateResponse(request, "privacy.html", {
        "email_verified": accounts.verified(owner) if owner else False,
        "privacy_contact": normalized(os.getenv("PLANET_PRIVACY_CONTACT", "")),
    })


@router.post("/privacidade/excluir")
@router.post("/api/auth/delete")
def delete(request: Request, password: str = Form(..., max_length=128), confirm: bool = Form(False)):
    owner = request.state.account_id
    if not confirm:
        raise HTTPException(400, "privacy.confirm")
    if not accounts.allow_request(f"delete:{owner}", 4, 60):
        raise HTTPException(429, "Too many requests")
    try:
        if not accounts.delete_account(owner, password):
            raise HTTPException(403, "privacy.password")
    except accounts.AccountDeletionBlocked:
        raise HTTPException(409, "privacy.blocked") from None
    response = (JSONResponse({"ok": True}) if request.url.path.startswith("/api/")
                else RedirectResponse("/privacidade", 303))
    response.delete_cookie(COOKIE)
    return response
