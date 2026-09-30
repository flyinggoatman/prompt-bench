"""Stripe events to memberships. Standard library only.

Stripe proves that a payment happened; Prompt Bench decides access. This
module does the first half only: it verifies that an event really came from
Stripe, and turns the few events that matter into changes to members.py's
entitlements. It never calls Stripe, holds no API key, and never sees a card.

The owner's rules (plan/05-implementation-strategy.md):
  a paid checkout           -> a lifetime membership
  a full refund             -> access ends at once
  a dispute opened          -> access continues, marked disputed
  a dispute lost            -> access ends
  a dispute won or closed   -> the mark is cleared
  a cancelled subscription  -> access continues to the end of the paid period
                               (for monthly plans, when there are any)

Configuration (environment):
  STRIPE_WEBHOOK_SECRET        whsec_... from the Stripe dashboard or CLI. Without
                               it the webhook answers 503 and nothing changes.
  BENCH_STRIPE_PAYMENT_LINKS   optional, comma separated plink_... ids that sell
                               the membership. When set, other checkouts are
                               recorded and ignored.
A checkout can also name the product itself with metadata product=mcp_membership.
"""

import hashlib
import hmac
import json
import os
import time

import members

WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
PAYMENT_LINKS = set(x.strip() for x in os.environ.get("BENCH_STRIPE_PAYMENT_LINKS", "").split(",") if x.strip())
TOLERANCE = 300           # seconds either side of the signed timestamp
PROVIDER = "stripe"


class BadSignature(Exception):
    pass


def ready():
    return bool(WEBHOOK_SECRET)


def verify(payload, header, secret=None, now=None):
    """The event, if the Stripe-Signature header is right for this exact body.

    Stripe signs "<timestamp>.<raw body>" with HMAC-SHA256 and the endpoint's
    secret, and may send several v1 signatures while a secret is being
    rolled. The body is checked as bytes, before it is parsed, and a timestamp
    outside the tolerance is refused so an old event cannot be replayed.
    """
    secret = secret if secret is not None else WEBHOOK_SECRET
    if not secret:
        raise BadSignature("no webhook secret is configured")
    parts = {}
    for item in (header or "").split(","):
        k, _, v = item.strip().partition("=")
        parts.setdefault(k, []).append(v)
    try:
        stamp = int(parts.get("t", [""])[0])
    except ValueError:
        raise BadSignature("no timestamp in the signature header")
    if abs((now if now is not None else time.time()) - stamp) > TOLERANCE:
        raise BadSignature("timestamp outside the tolerance")
    signed = str(stamp).encode() + b"." + payload
    want = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(want, sig) for sig in parts.get("v1", [])):
        raise BadSignature("no matching v1 signature")
    event = json.loads(payload.decode("utf-8"))
    if not isinstance(event, dict) or not event.get("id") or not event.get("type"):
        raise BadSignature("not a Stripe event")
    return event


def sign(payload, secret, stamp=None):
    """A Stripe-Signature header for a body, as Stripe would make it. For tests."""
    stamp = int(stamp if stamp is not None else time.time())
    sig = hmac.new(secret.encode(), str(stamp).encode() + b"." + payload, hashlib.sha256).hexdigest()
    return "t=%d,v1=%s" % (stamp, sig)


def sells_membership(session):
    meta = session.get("metadata") or {}
    if meta.get("product"):
        return meta["product"] == members.PRODUCT
    if PAYMENT_LINKS:
        return session.get("payment_link") in PAYMENT_LINKS
    # A Stripe account used only for Prompt Bench membership.
    return True


def handle(store, event):
    """Apply one verified event. Returns (status, detail): status is
    "processed" when it changed or confirmed something, "ignored" otherwise.
    Raises on a failure that Stripe should retry."""
    kind = event["type"]
    obj = (event.get("data") or {}).get("object") or {}

    if kind in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        if obj.get("mode") not in (None, "payment"):
            return "ignored", "not a one-off payment"
        if obj.get("payment_status") != "paid":
            return "ignored", "not paid yet (%s)" % obj.get("payment_status")
        if not sells_membership(obj):
            return "ignored", "not a membership checkout"
        sid = obj.get("id") or ""
        if store.checkout(sid):
            return "processed", "session already recorded"
        details = obj.get("customer_details") or {}
        cust = obj.get("customer")
        member = store.member_by_provider(PROVIDER, cust) if cust else None
        mid = member["member_id"] if member else store.create_member(
            name=str(details.get("name") or ""), email=str(details.get("email") or ""),
            notes="from Stripe checkout " + sid, provider=PROVIDER if cust else None,
            provider_customer_id=cust or None)
        existing = store.active_entitlement(mid)
        eid = existing["entitlement_id"] if existing else store.grant(
            mid, source="stripe", source_ref=obj.get("payment_intent") or sid, reason="paid checkout " + sid)
        store.record_checkout(sid, mid, eid)
        return "processed", "membership for " + mid

    if kind == "charge.refunded":
        ref = obj.get("payment_intent")
        full = obj.get("refunded") is True or (obj.get("amount_refunded") or 0) >= (obj.get("amount") or 1)
        ents = store.entitlements_by_ref(ref) if ref else []
        if not ents:
            return "ignored", "no membership for this payment"
        if not full:
            return "ignored", "partial refund: access unchanged"
        for e in ents:
            store.set_entitlement(e["entitlement_id"], status="revoked", reason="refunded")
        return "processed", "refunded: access ended"

    if kind in ("charge.dispute.created", "charge.dispute.updated", "charge.dispute.closed"):
        ents = store.entitlements_by_ref(obj.get("payment_intent")) if obj.get("payment_intent") else []
        if not ents:
            return "ignored", "no membership for this payment"
        status = obj.get("status")
        for e in ents:
            if kind == "charge.dispute.closed" and status == "lost":
                store.set_entitlement(e["entitlement_id"], status="revoked", disputed=False, reason="dispute lost")
            elif kind == "charge.dispute.closed":
                store.set_entitlement(e["entitlement_id"], disputed=False, reason="dispute closed: " + str(status))
            else:
                store.set_entitlement(e["entitlement_id"], disputed=True, reason="dispute open: " + str(status))
        return "processed", kind + " " + str(status)

    if kind == "customer.subscription.deleted":
        # Monthly plans do not exist yet. When they do, a cancellation keeps
        # access to the end of the period that was paid for.
        end = obj.get("current_period_end") or (obj.get("items", {}).get("data") or [{}])[0].get("current_period_end")
        ents = store.entitlements_by_ref(obj.get("id")) if obj.get("id") else []
        for e in ents:
            if end:
                store.set_entitlement(e["entitlement_id"], ends_at=members.now_iso(end), reason="cancelled: runs to period end")
        return ("processed", "cancelled to period end") if ents else ("ignored", "no membership for this subscription")

    return "ignored", "not an event membership uses"
