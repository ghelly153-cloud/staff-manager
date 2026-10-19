"""Masking of sensitive identifiers. Full values leave the server only on an explicit,
audited admin 'reveal' request - never in lists, exports, logs or reports."""
import re


def mask_aadhaar(v):
    if not v:
        return None
    d = re.sub(r"\D", "", str(v))
    return ("XXXX XXXX " + d[-4:]) if len(d) >= 4 else "XXXX"


def mask_mobile(v):
    if not v:
        return None
    d = re.sub(r"\D", "", str(v))
    return ("XXXXXX" + d[-4:]) if len(d) >= 4 else "XXXX"
