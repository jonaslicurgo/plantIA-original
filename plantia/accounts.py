"""SQLite account, session and one-time password recovery storage."""

import hashlib
import os
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from threading import BoundedSemaphore

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from plantia.database import get_engine
from plantia.i18n import catalog

HASHER = PasswordHasher()
HASH_SLOTS = BoundedSemaphore(4)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe())
SESSION_AGE = 7 * 86400


def initialize_accounts():
    with get_engine().begin() as db:
        db.execute(text("""CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL)"""))
        db.execute(text("""CREATE TABLE IF NOT EXISTS account_tokens (
            digest TEXT PRIMARY KEY, account_id INTEGER NOT NULL,
            purpose TEXT NOT NULL, expires INTEGER NOT NULL)"""))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_tokens_account ON account_tokens(account_id)"))
        db.execute(text("""CREATE TABLE IF NOT EXISTS rate_windows (
            bucket TEXT PRIMARY KEY, window INTEGER NOT NULL, hits INTEGER NOT NULL)"""))


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _password_hash(password):
    with HASH_SLOTS:
        return HASHER.hash(password)


def register(email, password):
    password_hash = _password_hash(password)
    try:
        with get_engine().begin() as db:
            db.execute(text("INSERT INTO accounts(email,password) VALUES (:email,:password)"),
                       {"email": email, "password": password_hash})
    except IntegrityError:
        return False
    return True


def _issue(db, account_id, purpose, age):
    token = secrets.token_urlsafe(32)
    db.execute(text("INSERT INTO account_tokens VALUES (:digest,:account,:purpose,:expires)"),
               {"digest": digest(token), "account": account_id, "purpose": purpose, "expires": int(time.time()) + age})
    return token


def login(email, password):
    with get_engine().connect() as db:
        row = db.execute(text("SELECT id,password FROM accounts WHERE email=:email AND suspended=0"), {"email": email}).first()
    try:
        with HASH_SLOTS:
            HASHER.verify(row.password if row else DUMMY_HASH, password)
    except VerifyMismatchError:
        return None
    if not row:
        return None
    # Recheck after hashing so a concurrent password reset cannot issue a stale session.
    with get_engine().begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        current = db.execute(text("SELECT password FROM accounts WHERE id=:id AND suspended=0"), {"id": row.id}).scalar()
        if current == row.password:
            db.execute(text("DELETE FROM account_tokens WHERE expires<=:now"), {"now": int(time.time())})
            return _issue(db, row.id, "session", SESSION_AGE)
    return None


def account_for(token):
    if not token or len(token) != 43:
        return None
    with get_engine().connect() as db:
        return db.execute(text("""SELECT account_id FROM account_tokens
            WHERE digest=:digest AND expires>:now AND purpose='session' AND account_id IN (SELECT id FROM accounts WHERE suspended=0)"""),
            {"digest": digest(token), "now": int(time.time())}).scalar()


def logout(token):
    if token:
        with get_engine().begin() as db:
            db.execute(text("DELETE FROM account_tokens WHERE digest=:digest AND purpose='session'"),
                       {"digest": digest(token)})


def issue_recovery(email):
    with get_engine().begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        account = db.execute(text("SELECT id FROM accounts WHERE email=:email"), {"email": email}).scalar()
        if account:
            db.execute(text("DELETE FROM account_tokens WHERE account_id=:id AND purpose='reset'"), {"id": account})
            return _issue(db, account, "reset", 1800)
    return None


def reset_password(token, password):
    if len(token) != 43:
        return False
    with get_engine().connect() as db:
        account = db.execute(text("""SELECT account_id FROM account_tokens
            WHERE digest=:digest AND purpose='reset' AND expires>:now"""),
            {"digest": digest(token), "now": int(time.time())}).scalar()
    if not account:
        return False
    password_hash = _password_hash(password)
    with get_engine().begin() as db:
        result = db.execute(text("""DELETE FROM account_tokens WHERE digest=:digest
            AND purpose='reset' AND expires>:now"""), {"digest": digest(token), "now": int(time.time())})
        if result.rowcount != 1:
            return False
        db.execute(text("UPDATE accounts SET password=:password WHERE id=:id"), {"password": password_hash, "id": account})
        db.execute(text("DELETE FROM account_tokens WHERE account_id=:id"), {"id": account})
    return True


def send_recovery(email, token, locale):
    strings = catalog(locale)
    message = EmailMessage()
    message["From"] = os.environ["PLANET_SMTP_FROM"]
    message["To"] = email
    message["Subject"] = f"PLANET-IA · {strings['Reset password']}"
    message.set_content(f"{os.environ['PLANET_PUBLIC_ORIGIN'].rstrip('/')}/conta/redefinir\n\n"
                        f"{strings['Recovery code']}\n{token}")
    with smtplib.SMTP_SSL(os.environ["PLANET_SMTP_HOST"], int(os.getenv("PLANET_SMTP_PORT", "465")), timeout=10, context=ssl.create_default_context()) as smtp:
        if os.getenv("PLANET_SMTP_USER"):
            smtp.login(os.environ["PLANET_SMTP_USER"], os.environ["PLANET_SMTP_PASSWORD"])
        smtp.send_message(message)


def allow_request(bucket, limit, seconds):
    now = int(time.time())
    window = now // seconds
    with get_engine().begin() as db:
        count = db.execute(text("""INSERT INTO rate_windows VALUES (:bucket,:window,1)
            ON CONFLICT(bucket) DO UPDATE SET hits=CASE WHEN window=:window THEN hits+1 ELSE 1 END,
            window=:window RETURNING hits"""), {"bucket": bucket, "window": window}).scalar_one()
        if secrets.randbelow(128) == 0:
            db.execute(text("DELETE FROM rate_windows WHERE window < CASE WHEN bucket LIKE 'ai:%' THEN :hour ELSE :minute END"),
                       {"hour": now // 3600 - 2, "minute": now // 60 - 2})
    return count <= limit
