from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import secrets
import sys
from urllib.parse import quote, unquote, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SECRET_PATH = ROOT / "data" / "remote-secrets.dpapi"
_ENTROPY = b"Daily Combo Trials remote secret store v1"


class SecretStoreError(RuntimeError):
    """Raised when encrypted local secret storage cannot be used safely."""


_PASSWORD_PLACEHOLDER_RE = re.compile(r"(?:\[your-password\]|<password>|your-password)", re.IGNORECASE)


@dataclass(frozen=True)
class SecretStatus:
    host: str
    port: int | None
    database: str
    saved_at: str


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _require_windows() -> None:
    if sys.platform != "win32":
        raise SecretStoreError("Windows DPAPI is required for this local setup store")


def _protect(payload: bytes) -> bytes:
    _require_windows()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    protect = crypt32.CryptProtectData
    protect.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    protect.restype = wintypes.BOOL
    local_free = kernel32.LocalFree
    local_free.argtypes = [ctypes.c_void_p]
    local_free.restype = ctypes.c_void_p

    payload_buffer = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
    entropy_buffer = (ctypes.c_ubyte * len(_ENTROPY)).from_buffer_copy(_ENTROPY)
    payload_blob = _DataBlob(len(payload), payload_buffer)
    entropy_blob = _DataBlob(len(_ENTROPY), entropy_buffer)
    protected_blob = _DataBlob()
    if not protect(
        ctypes.byref(payload_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        0,
        ctypes.byref(protected_blob),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(protected_blob.pbData, protected_blob.cbData)
    finally:
        local_free(protected_blob.pbData)


def _unprotect(ciphertext: bytes) -> bytes:
    _require_windows()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    unprotect = crypt32.CryptUnprotectData
    unprotect.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(ctypes.c_wchar_p),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    unprotect.restype = wintypes.BOOL
    local_free = kernel32.LocalFree
    local_free.argtypes = [ctypes.c_void_p]
    local_free.restype = ctypes.c_void_p

    ciphertext_buffer = (ctypes.c_ubyte * len(ciphertext)).from_buffer_copy(ciphertext)
    entropy_buffer = (ctypes.c_ubyte * len(_ENTROPY)).from_buffer_copy(_ENTROPY)
    ciphertext_blob = _DataBlob(len(ciphertext), ciphertext_buffer)
    entropy_blob = _DataBlob(len(_ENTROPY), entropy_buffer)
    plaintext_blob = _DataBlob()
    description = ctypes.c_wchar_p()
    if not unprotect(
        ctypes.byref(ciphertext_blob),
        ctypes.byref(description),
        ctypes.byref(entropy_blob),
        None,
        None,
        0,
        ctypes.byref(plaintext_blob),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(plaintext_blob.pbData, plaintext_blob.cbData)
    finally:
        local_free(plaintext_blob.pbData)
        if description.value:
            local_free(description)


def _has_password_placeholder(value: str) -> bool:
    return bool(_PASSWORD_PLACEHOLDER_RE.search(value))


def _with_database_password(connection_string: str, password: str) -> str:
    try:
        parseable_string = _PASSWORD_PLACEHOLDER_RE.sub("%5BYOUR-PASSWORD%5D", connection_string)
        parsed = urlsplit(parseable_string)
        username = parsed.username
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Enter a valid PostgreSQL connection string.") from exc

    if parsed.scheme not in {"postgres", "postgresql"} or not username or not hostname:
        raise ValueError("Enter the Supabase PostgreSQL connection string before entering its password.")

    encoded_username = quote(unquote(username), safe="!$&'()*+,;=")
    encoded_password = quote(password, safe="")
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    if port is not None:
        host = f"{host}:{port}"
    netloc = f"{encoded_username}:{encoded_password}@{host}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def compose_database_url(connection_string: str, password: str | None = None) -> str:
    """Combine Supabase's password placeholder URI with a separately entered password."""
    candidate = connection_string.strip()
    supplied_password = (password or "").strip()

    if not candidate:
        raise ValueError("Paste the Supabase connection string.")
    if any("\r" in value or "\n" in value for value in (candidate, supplied_password)):
        raise ValueError("The connection string and password cannot contain line breaks.")
    if len(candidate) > 2048 or len(supplied_password) > 1024:
        raise ValueError("The connection string or password is too long.")
    if supplied_password and _has_password_placeholder(supplied_password):
        raise ValueError("Enter the database password itself, not the placeholder text.")

    if supplied_password:
        return _with_database_password(candidate, supplied_password)
    if _has_password_placeholder(candidate):
        raise ValueError("Enter the database password in the separate password field.")
    return candidate


def _validate_database_url(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("Enter the Supabase transaction pooler connection string.")
    if len(candidate) > 2048 or "\r" in candidate or "\n" in candidate:
        raise ValueError("The connection string is too long or contains a line break.")
    lowered = candidate.lower()
    if any(marker in lowered for marker in ("[your-password]", "<password>", "your-password")):
        raise ValueError("Replace the password placeholder before saving the connection string.")
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
        username = parsed.username
        password = parsed.password
    except ValueError as exc:
        raise ValueError("Enter a valid PostgreSQL connection string.") from exc
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("Use the PostgreSQL URI from Supabase.")
    if not parsed.hostname or not username or password is None or not parsed.path.strip("/"):
        raise ValueError("The connection string must include its host, user, password, and database.")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("The connection string has an invalid port.")
    return candidate


def _status_for(value: str, saved_at: str) -> SecretStatus:
    parsed = urlsplit(value)
    return SecretStatus(
        host=parsed.hostname or "unknown",
        port=parsed.port,
        database=parsed.path.strip("/") or "unknown",
        saved_at=saved_at,
    )


class SecretStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_SECRET_PATH

    def save_database_url(self, value: str) -> SecretStatus:
        database_url = _validate_database_url(value)
        saved_at = datetime.now(timezone.utc).isoformat()
        document = {
            "version": 1,
            "provider": "supabase",
            "values": {"DATABASE_URL": database_url},
            "saved_at": saved_at,
        }
        payload = json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self._atomic_write(_protect(payload))
        return _status_for(database_url, saved_at)

    def load_database_url(self) -> str | None:
        document = self._load_document()
        if document is None:
            return None
        values = document.get("values")
        if not isinstance(values, dict) or not isinstance(values.get("DATABASE_URL"), str):
            raise SecretStoreError("The encrypted setup store is missing DATABASE_URL")
        return _validate_database_url(values["DATABASE_URL"])

    def status(self) -> SecretStatus | None:
        document = self._load_document()
        if document is None:
            return None
        saved_at = document.get("saved_at")
        if not isinstance(saved_at, str):
            raise SecretStoreError("The encrypted setup store is missing its save time")
        database_url = self.load_database_url()
        if database_url is None:
            raise SecretStoreError("The encrypted setup store is empty")
        return _status_for(database_url, saved_at)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)

    def _load_document(self) -> dict[str, object] | None:
        if not self.path.exists():
            return None
        try:
            document = json.loads(_unprotect(self.path.read_bytes()).decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SecretStoreError("The encrypted setup store could not be read") from exc
        if not isinstance(document, dict) or document.get("version") != 1:
            raise SecretStoreError("The encrypted setup store has an unsupported format")
        return document

    def _atomic_write(self, ciphertext: bytes) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{secrets.token_hex(8)}.tmp")
        try:
            with temporary.open("wb") as handle:
                handle.write(ciphertext)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
