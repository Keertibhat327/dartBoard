"""Local accounts use salted password hashes and revocable, opaque sessions."""

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def password_hash(password: str, salt: str | None = None) -> str:
    """A memory-hard derivation slows offline guesses; never store a password itself."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=64 * 1024 * 1024
    ).hex()
    return f"scrypt-v1${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    """Compare derived digests in constant time using the stored random salt."""
    version, salt, _ = encoded.split("$")
    return version == "scrypt-v1" and hmac.compare_digest(password_hash(password, salt), encoded)


def token_hash(token: str) -> str:
    """A database copy must not reveal usable session cookies."""
    return hashlib.sha256(token.encode()).hexdigest()


def email_address(value: Any) -> str:
    """Normalize local login IDs without claiming to verify ownership of an inbox."""
    if not isinstance(value, str) or len(value) > 254:
        raise ValueError("Enter a valid email address.")
    value = value.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValueError("Enter a valid email address.")
    return value


def display_name(value: Any) -> str:
    """Limit profile data to the name needed by the interface."""
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 80:
        raise ValueError("Enter a name between 1 and 80 characters.")
    return value.strip()


def new_password(value: Any) -> str:
    """Accept long passphrases while bounding password hashing input size."""
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise ValueError("Use a password between 12 and 128 characters.")
    return value


class Accounts:
    """SQLite is deliberately local-only; database roles are authoritative per request."""

    def __init__(self, path: Path, session_hours: int = 12) -> None:
        self.path = path
        self.session_seconds = session_hours * 3600
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'developer')),
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    key TEXT PRIMARY KEY, started_at INTEGER NOT NULL, count INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY, series TEXT NOT NULL, data_hash TEXT NOT NULL,
                    recorded_at INTEGER NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(series, data_hash)
                );
                CREATE TABLE IF NOT EXISTS uploads (
                    id INTEGER PRIMARY KEY, recorded_at INTEGER NOT NULL,
                    institution TEXT NOT NULL, assessment_type TEXT NOT NULL,
                    data_hash TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY, series TEXT NOT NULL,
                    target_id TEXT NOT NULL, target_year INTEGER NOT NULL,
                    target_sitting TEXT NOT NULL, recorded_at INTEGER NOT NULL,
                    payload TEXT NOT NULL, result TEXT,
                    UNIQUE(series, target_id), UNIQUE(series, target_year, target_sitting)
                );
            """)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Short transactions close their connection even when a request fails."""
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def public(row: sqlite3.Row) -> dict[str, Any]:
        """Whitelist profile fields so hashes and session material cannot reach the browser."""
        return {key: row[key] for key in ("id", "email", "name", "role", "created_at")}

    def register(self, email: Any, name: Any, password: Any) -> dict[str, Any]:
        email, name, password = email_address(email), display_name(name), new_password(password)
        encoded = password_hash(password)
        try:
            with self.connection() as db:
                db.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?, 'user', ?)",
                    (secrets.token_hex(16), email, name, encoded, int(time.time())),
                )
                return self.public(
                    db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Unable to create this account. Try signing in instead.") from exc

    def login(self, email: Any, password: Any) -> str | None:
        email = email_address(email)
        if not isinstance(password, str) or len(password) > 128:
            return None
        with self.connection() as db:
            row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        # An absent user still pays the password-derivation cost.
        encoded = row["password_hash"] if row else "scrypt-v1$" + "00" * 16 + "$" + "00" * 64
        if not verify_password(password, encoded) or row is None:
            return None
        return self.create_session(row["id"])

    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with self.connection() as db:
            db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?)",
                (token_hash(token), user_id, now + self.session_seconds),
            )
        return token

    def user(self, token: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                """SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?""",
                (token_hash(token), int(time.time())),
            ).fetchone()
        return self.public(row) if row else None

    def logout(self, token: str) -> None:
        with self.connection() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))

    def update_name(self, user_id: str, name: Any) -> None:
        name = display_name(name)
        with self.connection() as db:
            db.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))

    def change_password(self, user_id: str, current: Any, replacement: Any) -> bool:
        replacement = new_password(replacement)
        if not isinstance(current, str) or len(current) > 128:
            return False
        with self.connection() as db:
            row = db.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None or not verify_password(current, row[0]):
                return False
            db.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash(replacement), user_id),
            )
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        return True

    def grant_developer(self, email: str) -> None:
        """Only a local operator command can grant this role; signup has no role input."""
        with self.connection() as db:
            cursor = db.execute(
                "UPDATE users SET role = 'developer' WHERE email = ?", (email_address(email),)
            )
            if cursor.rowcount != 1:
                raise ValueError("Account not found. Create your account in the app first.")

    def allow_attempt(self, key: str, limit: int) -> bool:
        """Persist local rate limits across restarts; do not log passwords or email addresses."""
        now = int(time.time())
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM attempts WHERE started_at < ?", (now - 60,))
            db.execute(
                "INSERT INTO attempts VALUES (?, ?, 1) "
                "ON CONFLICT(key) DO UPDATE SET count=count+1",
                (token_hash(key), now),
            )
            count = db.execute(
                "SELECT count FROM attempts WHERE key = ?", (token_hash(key),)
            ).fetchone()[0]
        return count <= limit
