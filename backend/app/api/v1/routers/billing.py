"""Subscription endpoints: checkout, self-service portal, webhook, status."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.api.deps import CurrentUser, DbSession, rate_limiter, record_audit
from app.core.logging import get_logger
from app.db.models.ops import AuditAction
from app.services import billing

logger = get_logger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/checkout", dependencies=[Depends(rate_limiter("auth"))])
def start_checkout(request: Request, db: DbSession, user: CurrentUser) -> dict:
    """Begin a Stripe Checkout session for the paid tier."""
    try:
        url = billing.create_checkout_session(db, user)
    except billing.BillingNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except billing.BillingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record_audit(db, AuditAction.BILLING_CHECKOUT_STARTED, actor=user, request=request)
    db.commit()
    return {"url": url}


@router.post("/portal", dependencies=[Depends(rate_limiter("auth"))])
def open_portal(request: Request, db: DbSession, user: CurrentUser) -> dict:
    """Return a Billing Portal URL for cancelling or changing the plan."""
    try:
        url = billing.create_portal_session(db, user)
    except billing.BillingNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except billing.BillingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record_audit(db, AuditAction.BILLING_PORTAL_OPENED, actor=user, request=request)
    db.commit()
    return {"url": url}


@router.get("/status")
def get_status(user: CurrentUser) -> dict:
    """Current tier and subscription state, for rendering the billing page."""
    return billing.billing_status(user)


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    db: DbSession,
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> dict:
    """Receive subscription events from Stripe.

    Deliberately carries no auth dependency — Stripe calls this directly and holds no
    bearer token — so the signature check inside `verify_webhook` is the entire access
    control for this route. The raw body is read before any parsing, because the
    signature covers the exact bytes Stripe sent and re-serialising JSON would change
    them.

    A verification failure answers 400 rather than 401: Stripe treats any non-2xx as a
    delivery failure and retries, and 400 is what its own documentation expects for a
    body it should not have sent.
    """
    payload = await request.body()

    try:
        event = billing.verify_webhook(payload, stripe_signature)
    except billing.BillingNotConfigured as exc:
        logger.error("billing.webhook_unconfigured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except billing.BillingError as exc:
        logger.warning("billing.webhook_rejected", reason=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        billing.handle_webhook_event(db, event)
    except billing.BillingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Stripe only needs a 2xx; the body is for a human reading delivery logs.
    return {"received": True}


__all__ = ["router"]
