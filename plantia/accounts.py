"""SQLite account, session and one-time password recovery storage."""

from contextlib import closing
import hashlib
from http.client import HTTPException, HTTPSConnection
import json
import logging
from pathlib import Path
import os
import secrets
import time
from threading import BoundedSemaphore

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from plantia.config import UPLOADS_DIR
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
        if "email_verified" not in {row[1] for row in db.exec_driver_sql("PRAGMA table_info(accounts)")}:
            db.exec_driver_sql("ALTER TABLE accounts ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
        db.exec_driver_sql("""CREATE TABLE IF NOT EXISTS botanical_source_cache (
            key TEXT PRIMARY KEY, payload TEXT NOT NULL, expires INTEGER NOT NULL)""")
        db.exec_driver_sql("CREATE INDEX IF NOT EXISTS botanical_cache_expiry ON botanical_source_cache(expires)")
        db.exec_driver_sql("""CREATE TABLE IF NOT EXISTS botanical_favorites (
            account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            species_id TEXT NOT NULL, PRIMARY KEY(account_id, species_id))""")
        db.exec_driver_sql("CREATE TABLE IF NOT EXISTS account_photo_cleanup (name TEXT PRIMARY KEY)")
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


def verification_required():
    return os.getenv("PLANET_REQUIRE_VERIFIED_EMAIL") == "1"


def verified(account_id):
    with get_engine().connect() as db:
        return bool(db.execute(text("SELECT email_verified FROM accounts WHERE id=:id"), {"id": account_id}).scalar())


def issue_verification(email):
    with get_engine().begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        account = db.execute(text("""SELECT id FROM accounts
            WHERE email=:email AND suspended=0 AND email_verified=0"""), {"email": email}).scalar()
        if account:
            db.execute(text("DELETE FROM account_tokens WHERE account_id=:id AND purpose='verify'"), {"id": account})
            return _issue(db, account, "verify", 1800)
    return None


def verify_email(token, password):
    if len(token) != 43:
        return False
    params = {"digest": digest(token), "now": int(time.time())}
    with get_engine().connect() as db:
        row = db.execute(text("""SELECT a.password FROM account_tokens t JOIN accounts a ON a.id=t.account_id
            WHERE t.digest=:digest AND t.purpose='verify' AND t.expires>:now AND a.suspended=0"""), params).first()
    if not row:
        return False
    try:
        with HASH_SLOTS:
            HASHER.verify(row.password, password)
    except VerifyMismatchError:
        return False
    with get_engine().begin() as db:
        account = db.execute(text("""DELETE FROM account_tokens WHERE digest=:digest AND purpose='verify'
            AND expires>:now AND account_id IN (SELECT id FROM accounts WHERE suspended=0 AND password=:password)
            RETURNING account_id"""), {**params, "now": int(time.time()), "password": row.password}).scalar()
        if not account:
            return False
        db.execute(text("UPDATE accounts SET email_verified=1 WHERE id=:id"), {"id": account})
        # Sessions that predate proof of mailbox ownership must never acquire its privileges.
        db.execute(text("DELETE FROM account_tokens WHERE account_id=:id AND purpose='session'"), {"id": account})
    return True


class AccountDeletionBlocked(Exception):
    pass


def delete_account(owner, password):
    with get_engine().connect() as db:
        old_hash = db.execute(text("SELECT password FROM accounts WHERE id=:id AND suspended=0"), {"id": owner}).scalar()
    try:
        with HASH_SLOTS:
            HASHER.verify(old_hash or DUMMY_HASH, password)
    except VerifyMismatchError:
        return False
    with get_engine().begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        params = {"id": owner, "now": int(time.time())}
        account = db.execute(text("""SELECT password,commercial_role FROM accounts
            WHERE id=:id AND suspended=0"""), params).first()
        if not account or account.password != old_hash:
            return False
        if account.commercial_role != "member" or db.execute(text("""SELECT 1 FROM billing_customers WHERE account_id=:id
                UNION ALL SELECT 1 FROM subscriptions WHERE account_id=:id
                UNION ALL SELECT 1 FROM checkout_pending WHERE account_id=:id AND expires>:now"""), params).first():
            raise AccountDeletionBlocked
        for path in db.execute(text("SELECT image_path FROM plantas WHERE owner_id=:id"), params).scalars():
            name = Path(path).name
            if name and name not in {".", ".."}:
                db.execute(text("INSERT OR IGNORE INTO account_photo_cleanup VALUES (:name)"), {"name": name})
        for table in ("plantas", "health_ai_usage"):
            db.exec_driver_sql(f"DELETE FROM {table} WHERE owner_id=?", (owner,))
        for table in ("account_tokens", "checkout_pending", "ai_meter"):
            db.exec_driver_sql(f"DELETE FROM {table} WHERE account_id=?", (owner,))
        db.execute(text("UPDATE billing_events SET account_id=NULL WHERE account_id=:id"), params)
        db.execute(text("DELETE FROM commercial_audit WHERE target=:target AND action IN ('account.edit','credits.grant')"), {"target": str(owner)})
        db.execute(text("DELETE FROM accounts WHERE id=:id"), params)
    clean_deleted_photos()
    return True


def clean_deleted_photos():
    with get_engine().begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        names = db.execute(text("SELECT name FROM account_photo_cleanup")).scalars().all()
        for name in names:
            try:
                referenced = db.execute(text("""SELECT 1 FROM plantas
                    WHERE image_path=:name OR substr(image_path,-length(:name)-1)='/'||:name LIMIT 1"""),
                    {"name": name}).first()
                if referenced:
                    continue
                (UPLOADS_DIR / name).unlink(missing_ok=True)
                db.execute(text("DELETE FROM account_photo_cleanup WHERE name=:name"), {"name": name})
            except OSError:
                logging.getLogger(__name__).warning("PLANET-IA pending photo cleanup")


def email_delivery_configured():
    return all(os.getenv(key, "").strip() for key in (
        "PLANET_PUBLIC_ORIGIN", "PLANET_RESEND_API_KEY", "PLANET_RESEND_FROM",
    ))


def send_recovery(email, token, locale):
    _send_code(email, token, locale, "Reset password", "Recovery code", "redefinir")


def send_verification(email, token, locale):
    _send_code(email, token, locale, "privacy.verify", "privacy.code", "verificar")


def _send_code(email, token, locale, subject, code, page):
    strings = catalog(locale)
    payload = {
        "from": os.environ["PLANET_RESEND_FROM"].strip(),
        "to": [email],
        "subject": f"PLANET-IA · {strings[subject]}",
        "text": f"{os.environ['PLANET_PUBLIC_ORIGIN'].rstrip('/')}/conta/{page}\n\n{strings[code]}\n{token}",
    }
    headers = {
        "Authorization": "Bearer " + os.environ["PLANET_RESEND_API_KEY"].strip(),
        "Content-Type": "application/json",
        "User-Agent": "PLANET-IA/1.0",
    }
    # Use system TLS verification and never follow redirects with the key or code.
    try:
        with closing(HTTPSConnection("api.resend.com", timeout=10)) as connection:
            connection.request("POST", "/emails", body=json.dumps(payload).encode("utf-8"), headers=headers)
            with closing(connection.getresponse()) as response:
                if not 200 <= response.status < 300:
                    raise OSError(f"Resend rejected email (HTTP {response.status})")
    except HTTPException:
        raise OSError("Invalid response from Resend") from None


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
