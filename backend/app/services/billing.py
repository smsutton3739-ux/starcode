"""Stripe Checkout, the customer portal, and webhook-driven subscription state.

Stripe is the system of record. This module's job is to mirror just enough of it onto the
`users` row to answer one question on the request path — may this account see interpretive
claims — without calling Stripe to find out.

Two rules shape everything here:

**Nothing writes subscription state without a verified signature.** The webhook route
carries no auth dependency, because Stripe calls it directly and has no bearer token. The
signature check inside `handle_webhook_event` is therefore the *only* thing standing
between an anonymous HTTP request and a free upgrade to the paid tier. It is not optional
and it is not skippable in production.

**Every effect is idempotent.** Stripe retries until it gets a 2xx and does not promise
exactly-once delivery, so the same event arrives more than once in normal operation. Each
event id is recorded in `processed_stripe_events` inside the same transaction as the
change it caused; a replay finds the id and returns without re-applying.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.ops import ProcessedStripeEvent
from app.db.models.user import Tier, User

logger = get_logger(__name__)


class BillingError(RuntimeError):
    """Raised when billing cannot proceed, with a message meant for the caller."""


class BillingNotConfigured(BillingError):
    """Billing is switched off on this deployment."""


#: Stripe subscription statuses that entitle the account to the paid tier.
#:
#: `past_due` is deliberately included: the customer has paid before and Stripe is still
#: retrying the card. Cutting access at the first failed charge punishes an expired card
#: the same as a cancellation, and Stripe will move the subscription to `canceled` or
#: `unpaid` on its own once its retry schedule is exhausted. `unpaid` is excluded, which
#: is where that schedule ends.
ENTITLING_STATUSES = frozenset({"active", "trialing", "past_due"})


def _stripe() -> Any:
    """The configured Stripe client, or a refusal that names the missing setting.

    Imported lazily rather than at module scope so that the rest of the application — and
    the whole test suite — runs with no Stripe credentials and no network, which is the
    same arrangement the Anthropic provider uses.
    """
    if not settings.STRIPE_SECRET_KEY:
        raise BillingNotConfigured(
            "Billing is not configured on this deployment: STRIPE_SECRET_KEY is unset. "
            "Set it, along with STRIPE_PRICE_ID_PAID and STRIPE_WEBHOOK_SECRET, to enable "
            "checkout."
        )
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def _frontend_url(path: str) -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}{path}"


def ensure_customer(db: Session, user: User) -> str:
    """The Stripe customer id for this user, creating one on first use.

    Stored back on the user so a returning customer keeps one customer record rather than
    accumulating a new one per checkout, which would scatter their invoice history.
    """
    if user.stripe_customer_id:
        return user.stripe_customer_id

    stripe = _stripe()
    customer = stripe.Customer.create(
        email=user.email,
        name=user.display_name or None,
        # Lets a human answer "which account is this?" from the Stripe dashboard, and
        # lets the webhook find the user even if the client reference is missing.
        metadata={"user_id": user.id},
    )
    user.stripe_customer_id = customer["id"]
    db.commit()
    return user.stripe_customer_id


def create_checkout_session(db: Session, user: User) -> str:
    """Start a Checkout session for the paid tier and return its URL."""
    if not settings.billing_enabled:
        raise BillingNotConfigured(
            "Billing is not configured on this deployment. STRIPE_SECRET_KEY and "
            "STRIPE_PRICE_ID_PAID must both be set."
        )
    if user.tier is Tier.PAID and user.subscription_status in ENTITLING_STATUSES:
        raise BillingError("This account already has an active paid subscription.")

    stripe = _stripe()
    customer_id = ensure_customer(db, user)
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": settings.STRIPE_PRICE_ID_PAID, "quantity": 1}],
        success_url=_frontend_url(settings.BILLING_SUCCESS_PATH),
        cancel_url=_frontend_url(settings.BILLING_CANCEL_PATH),
        # Both carried so the webhook can resolve the user even if one is absent.
        client_reference_id=user.id,
        metadata={"user_id": user.id},
        subscription_data={"metadata": {"user_id": user.id}},
    )
    url = session.get("url")
    if not url:
        raise BillingError("Stripe did not return a checkout URL.")
    return str(url)


def create_portal_session(db: Session, user: User) -> str:
    """Return a Billing Portal URL so the customer can cancel or change plan themselves."""
    if not user.stripe_customer_id:
        raise BillingError(
            "This account has no billing history yet, so there is nothing to manage. "
            "Subscribe first."
        )
    stripe = _stripe()
    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=_frontend_url("/billing"),
    )
    url = session.get("url")
    if not url:
        raise BillingError("Stripe did not return a portal URL.")
    return str(url)


def verify_webhook(payload: bytes, signature: str | None) -> dict:
    """Parse a webhook body only after its signature checks out.

    Refuses outright when no signing secret is configured. The alternative — accepting
    unsigned events when the secret happens to be missing — would mean a misconfigured
    deployment silently accepts subscription writes from anyone who can reach the URL.
    """
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise BillingNotConfigured(
            "STRIPE_WEBHOOK_SECRET is not set, so webhook signatures cannot be verified "
            "and this endpoint refuses every request. Set it to the signing secret shown "
            "when the endpoint is registered in the Stripe dashboard."
        )
    if not signature:
        raise BillingError("Missing Stripe-Signature header.")

    stripe = _stripe()
    try:
        event = stripe.Webhook.construct_event(payload, signature, settings.STRIPE_WEBHOOK_SECRET)
    except Exception as exc:  # stripe raises its own types; all of them mean "reject"
        raise BillingError(f"Stripe signature verification failed: {exc}") from exc
    return dict(event)


def _user_for_event(db: Session, obj: dict) -> User | None:
    """Find the account an event belongs to.

    Tried in order of reliability: our own id echoed back through metadata, then the
    customer id we stored at checkout. Returning None is normal rather than exceptional —
    events for customers created outside this application exist, and are ignored.
    """
    metadata = obj.get("metadata") or {}
    user_id = metadata.get("user_id") or obj.get("client_reference_id")
    if user_id:
        user = db.get(User, user_id)
        if user is not None:
            return user

    customer_id = obj.get("customer")
    if isinstance(customer_id, str):
        return db.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        ).scalar_one_or_none()
    return None


def _apply_subscription(user: User, subscription: dict) -> None:
    status = str(subscription.get("status") or "")
    user.stripe_subscription_id = subscription.get("id") or user.stripe_subscription_id
    user.subscription_status = status or None

    # BYOK is a standing arrangement rather than something Stripe knows about, so a
    # subscription event must not knock a BYOK account down to free.
    if user.tier is Tier.BYOK:
        return
    user.tier = Tier.PAID if status in ENTITLING_STATUSES else Tier.FREE


def handle_webhook_event(db: Session, event: dict) -> None:
    """Apply one verified event, exactly once.

    The event id is inserted first and committed together with the change it causes, so a
    crash between the two cannot leave an event marked processed that never took effect.
    A concurrent duplicate loses the insert on the primary key and returns quietly.
    """
    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    if not event_id:
        raise BillingError("Stripe event has no id.")

    if db.get(ProcessedStripeEvent, event_id) is not None:
        logger.info("billing.webhook_replayed", event_id=event_id, event_type=event_type)
        return

    db.add(ProcessedStripeEvent(id=event_id, event_type=event_type))
    try:
        db.flush()
    except IntegrityError:
        # Another delivery of the same event committed while we were working.
        db.rollback()
        logger.info("billing.webhook_race_replay", event_id=event_id, event_type=event_type)
        return

    obj = (event.get("data") or {}).get("object") or {}
    user = _user_for_event(db, obj)

    if user is None:
        # Still recorded as processed: an event we cannot attribute will not become
        # attributable on retry, and Stripe would otherwise redeliver it indefinitely.
        db.commit()
        logger.warning("billing.webhook_no_user", event_id=event_id, event_type=event_type)
        return

    if event_type == "checkout.session.completed":
        # The session carries only the subscription id; its status arrives on the
        # subscription events that follow. Treating a completed checkout as paid here
        # avoids a window where the customer has paid and the site still says free.
        user.stripe_subscription_id = obj.get("subscription") or user.stripe_subscription_id
        if user.tier is not Tier.BYOK:
            user.tier = Tier.PAID
            user.subscription_status = "active"

    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        _apply_subscription(user, obj)

    elif event_type == "customer.subscription.deleted":
        user.stripe_subscription_id = None
        user.subscription_status = str(obj.get("status") or "canceled")
        if user.tier is not Tier.BYOK:
            user.tier = Tier.FREE

    elif event_type == "invoice.payment_failed":
        # Recorded, but access is not cut here: Stripe is still retrying, and the
        # subscription events above are what actually move the tier.
        user.subscription_status = "past_due"

    else:
        logger.info("billing.webhook_ignored", event_id=event_id, event_type=event_type)

    db.commit()
    logger.info(
        "billing.webhook_applied",
        event_id=event_id,
        event_type=event_type,
        user_id=user.id,
        tier=user.tier.value,
        subscription_status=user.subscription_status,
    )


def billing_status(user: User) -> dict:
    """What the frontend needs to render the billing page."""
    return {
        "tier": user.tier.value,
        "subscription_status": user.subscription_status,
        "has_subscription": bool(user.stripe_subscription_id),
        "can_manage": bool(user.stripe_customer_id),
        "billing_enabled": settings.billing_enabled,
        "unlocks_interpretation": user.tier.unlocks_interpretation,
        "byok_key_last4": user.byok_anthropic_key_last4,
    }


__all__ = [
    "BillingError",
    "BillingNotConfigured",
    "ENTITLING_STATUSES",
    "ensure_customer",
    "create_checkout_session",
    "create_portal_session",
    "verify_webhook",
    "handle_webhook_event",
    "billing_status",
]
