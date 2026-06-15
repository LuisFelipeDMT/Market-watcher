"""Mobile gateway: a unified proposal feed, push delivery, and the 2FA surface
the phone app consumes (all in the analysis zone, behind dashboard auth)."""

from app.mobile.devices import DeviceRegistry
from app.mobile.feed import build_proposals
from app.mobile.models import AssetClass, DeviceRegistration, Proposal
from app.mobile.push import PushAlertSink, build_push_sender
from app.mobile.twofa_gateway import build_twofa_gateway

__all__ = [
    "AssetClass",
    "DeviceRegistration",
    "DeviceRegistry",
    "Proposal",
    "PushAlertSink",
    "build_proposals",
    "build_push_sender",
    "build_twofa_gateway",
]
