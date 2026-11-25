"""Parsing of /jump arguments."""

import re

UNITS = {"s": 1, "m": 60, "h": 3600}
_REL = re.compile(r"^([+-])?\s*(\d+(?:[.,]\d+)?)\s*([smh])?$", re.IGNORECASE)
_ABS = re.compile(r"^(?:(\d{1,2}):)?(\d{1,3}):(\d{2})$")


def parse_jump(text: str):
    """('to', seconds) for "1:30" / "01:02:03" / "0", ('delta', seconds) for "30", "+2m", "-10", "-40s", "1h".
    No sign = ahead. None when it is not a time."""
    text = text.strip().replace(" ", "")
    found = _ABS.match(text)
    if found:
        h, m, s = (int(x) if x else 0 for x in found.groups())
        return "to", h * 3600 + m * 60 + s
    found = _REL.match(text)
    if not found:
        return None
    sign, number, unit = found.groups()
    seconds = int(round(float(number.replace(",", ".")) * UNITS[(unit or "s").lower()]))
    if seconds == 0 and not sign:
        return "to", 0
    return "delta", -seconds if sign == "-" else seconds
