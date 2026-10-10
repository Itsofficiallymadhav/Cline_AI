import re
import unicodedata

AMOUNT_RE = re.compile(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:रुपये|रुपए|rupees)", re.I)


def normalize_digits(text: str) -> str:
    """Any Unicode digits (Devanagari, Bengali, Tamil...) -> ASCII 0-9."""
    return "".join(str(unicodedata.digit(c)) if c.isdigit() else c for c in text)


def amounts_in(text: str) -> set[float]:
    out = set()
    for m in AMOUNT_RE.finditer(normalize_digits(text)):
        raw = (m.group(1) or m.group(2)).replace(",", "").rstrip(".")
        try:
            out.add(round(float(raw), 2))
        except ValueError:
            pass
    return out


def fmt_money(x) -> str:
    if x is None:
        return "-"
    return f"{x:g}" if float(x).is_integer() else f"{x:.2f}"
