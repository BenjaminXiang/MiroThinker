"""Admin console authentication endpoints (login, session, account management).

Every refusal is a stable code the page can render: ``invalid_credentials``,
``authentication_required``, ``account_exists``, ``last_account``,
``current_password_incorrect``, or the login lockout payload.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from backend.services.admin_auth import (
    AccountNotFoundError,
    AdminAuthError,
    AdminAuthStore,
    AdminLoginThrottle,
    DuplicateAccountError,
    InvalidPasswordError,
    LastAccountError,
    generate_password,
    store_from_environment,
)
from backend.services.admin_session import (
    SessionTicket,
    clear_session_cookie,
    issue_session,
    render_session_cookie,
    request_is_https,
    session_ticket,
)

router = APIRouter(prefix="/api/auth", tags=["admin-auth"])

# One limiter per process: five wrong passwords must not become a guessing oracle.
_LOGIN_LIMITER = AdminLoginThrottle()
_AUTHENTICATION_REQUIRED = "authentication_required"


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    new_password: str
    current_password: str | None = None


class AccountCreateRequest(BaseModel):
    username: str
    password: str | None = None


class AccountPasswordRequest(BaseModel):
    password: str | None = None


def _client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _store() -> AdminAuthStore:
    return store_from_environment()


def _authenticated(request: Request) -> SessionTicket:
    """The caller's session; every endpoint below is meaningful only with one."""

    ticket = session_ticket(request)
    if ticket is None:
        raise HTTPException(status_code=401, detail=_AUTHENTICATION_REQUIRED)
    return ticket


def _session_payload(
    store: AdminAuthStore,
    username: str,
    response: Response,
    request: Request,
    *,
    issued: tuple[str, datetime] | None = None,
) -> dict[str, Any]:
    account = store.account(username)
    if account is None:
        raise HTTPException(status_code=401, detail=_AUTHENTICATION_REQUIRED)
    token, expires_at = issued or issue_session(username)
    response.headers["Set-Cookie"] = render_session_cookie(
        token, secure=request_is_https(request), expires_at=expires_at
    )
    return {
        "username": account.username,
        "role": account.role,
        "expires_at": expires_at.astimezone(UTC).isoformat(),
    }


def _audit(
    store: AdminAuthStore,
    request: Request,
    *,
    actor: str,
    action: str,
    target: str = "",
    result: str = "ok",
    detail: str | None = None,
) -> None:
    store.append_audit(
        actor=actor,
        action=action,
        target=target,
        source_ip=_client_ip(request),
        result=result,
        detail=detail,
    )


@router.post("/login")
def login(request: Request, response: Response, body: LoginRequest) -> dict[str, Any]:
    store = _store()
    key = f"login:{body.username}:{_client_ip(request)}"
    decision = _LOGIN_LIMITER.check(key)
    if not decision.allowed:
        _audit(
            store,
            request,
            actor=body.username,
            action="login",
            target=body.username,
            result="locked",
            detail="lockout",
        )
        raise HTTPException(
            status_code=429,
            detail={
                "error": "locked",
                "retry_after_seconds": decision.retry_after_seconds,
            },
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    if not store.verify_credentials(body.username, body.password):
        _audit(
            store,
            request,
            actor=body.username,
            action="login",
            target=body.username,
            result="fail",
            detail="invalid_credentials",
        )
        _LOGIN_LIMITER.record_failure(key)
        raise HTTPException(status_code=401, detail="invalid_credentials")
    _LOGIN_LIMITER.record_success(key)
    _audit(
        store,
        request,
        actor=body.username,
        action="login",
        target=body.username,
    )
    return _session_payload(store, body.username, response, request)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    ticket: SessionTicket = Depends(_authenticated),
) -> dict[str, Any]:
    store = _store()
    _audit(store, request, actor=ticket.username, action="logout", target=ticket.username)
    response.headers["Set-Cookie"] = clear_session_cookie(secure=request_is_https(request))
    return {"username": ticket.username, "logged_out": True}


@router.get("/me")
def me(
    request: Request, ticket: SessionTicket = Depends(_authenticated)
) -> dict[str, Any]:
    del request
    account = _store().account(ticket.username)
    if account is None:
        raise HTTPException(status_code=401, detail=_AUTHENTICATION_REQUIRED)
    return {
        "username": account.username,
        "role": account.role,
        "expires_at": ticket.expires_at.astimezone(UTC).isoformat(),
    }


@router.post("/password")
def change_password(
    request: Request,
    response: Response,
    body: PasswordChangeRequest,
    ticket: SessionTicket = Depends(_authenticated),
) -> dict[str, Any]:
    store = _store()
    if body.current_password is not None and not store.verify_credentials(
        ticket.username, body.current_password
    ):
        _audit(
            store,
            request,
            actor=ticket.username,
            action="password_change",
            target=ticket.username,
            result="fail",
            detail="current_password_incorrect",
        )
        raise HTTPException(status_code=403, detail="current_password_incorrect")
    try:
        store.set_password(ticket.username, body.new_password)
    except InvalidPasswordError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=401, detail=_AUTHENTICATION_REQUIRED) from exc
    _audit(store, request, actor=ticket.username, action="password_change", target=ticket.username)
    # Every prior cookie for this account dies with the epoch bump; the caller
    # keeps working because the answer carries a freshly signed session.
    return _session_payload(store, ticket.username, response, request)


@router.get("/accounts")
def list_accounts(ticket: SessionTicket = Depends(_authenticated)) -> dict[str, Any]:
    del ticket
    return {"accounts": [account.as_public_dict() for account in _store().accounts()]}


@router.post("/accounts", status_code=201)
def create_account(
    request: Request,
    body: AccountCreateRequest,
    ticket: SessionTicket = Depends(_authenticated),
) -> dict[str, Any]:
    store = _store()
    generated = None if body.password else generate_password()
    try:
        account = store.create_account(body.username, body.password or generated or "")
    except DuplicateAccountError as exc:
        _audit(
            store,
            request,
            actor=ticket.username,
            action="account_create",
            target=body.username,
            result="fail",
            detail="account_exists",
        )
        raise HTTPException(status_code=409, detail="account_exists") from exc
    except (InvalidPasswordError, AdminAuthError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(store, request, actor=ticket.username, action="account_create", target=account.username)
    return {"account": account.as_public_dict(), "password": generated}


@router.delete("/accounts/{username}")
def delete_account(
    request: Request,
    username: str,
    ticket: SessionTicket = Depends(_authenticated),
) -> dict[str, Any]:
    store = _store()
    try:
        deleted = store.delete_account(username)
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="account_not_found") from exc
    except LastAccountError as exc:
        _audit(
            store,
            request,
            actor=ticket.username,
            action="account_delete",
            target=username,
            result="fail",
            detail="last_account",
        )
        raise HTTPException(status_code=409, detail="last_account") from exc
    _audit(store, request, actor=ticket.username, action="account_delete", target=deleted.username)
    return {"deleted": deleted.username}


@router.post("/accounts/{username}/password")
def reset_account_password(
    request: Request,
    username: str,
    ticket: SessionTicket = Depends(_authenticated),
    body: AccountPasswordRequest | None = None,
) -> dict[str, Any]:
    store = _store()
    provided = body.password if body is not None else None
    generated = None if provided else generate_password()
    try:
        account = store.set_password(username, provided or generated or "")
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="account_not_found") from exc
    except (InvalidPasswordError, AdminAuthError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(
        store,
        request,
        actor=ticket.username,
        action="password_reset",
        target=account.username,
    )
    return {"account": account.as_public_dict(), "password": generated}


__all__ = ["router"]
