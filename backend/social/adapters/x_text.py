"""Pinned twitter-text v3 weights, NFC and the official twemoji expression.

Explicit HTTP(S) URLs are the admitted application subset. Bare domains are
reported for correction rather than guessed by an incomplete TLD recognizer.
"""
from __future__ import annotations

from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit


_source = (Path(__file__).with_name("x_vendor") / "emoji-regex.js.txt").read_text()
_EMOJI = re.compile(_source.split("export default /", 1)[1].rsplit("/g;", 1)[0])
_URL = re.compile(r"https?://[^\s<>\x00-\x20]+", re.IGNORECASE)
_DOMAIN = re.compile(r"(?<![\w@])(?:[\w-]+\.)+[A-Za-z\u0080-\uffff]{2,}(?:[/?:#][^\s<>]*)?", re.UNICODE)


def render_text(payload):
    parts = [payload.text]
    if payload.hashtags:
        parts.append(" ".join(tag if tag.startswith("#") else "#" + tag for tag in payload.hashtags))
    if payload.link:
        parts.append(payload.link)
    return unicodedata.normalize("NFC", "\n\n".join(part for part in parts if part))


def _urls(text):
    for match in _URL.finditer(text):
        url = match.group().rstrip(".,!?;:'\"")
        while url.endswith(")") and url.count(")") > url.count("("):
            url = url[:-1]
        parsed = urlsplit(url)
        if (not parsed.hostname or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+", parsed.hostname)
                or parsed.username or parsed.password
                or parsed.port is not None and not 1 <= parsed.port <= 65535
                or "\\" in url or any(ord(c) > 127 for c in url)):
            raise ValueError("Use an explicit ASCII HTTP(S) URL with a domain name")
        yield match.start(), match.start() + len(url), url


def count_text(text):
    """Return a weighted count for the explicitly admitted URL subset.

    The generated expression is unchanged JavaScript UTF-16. Matching against
    code units preserves its surrogate ranges; outside matches we count Unicode
    code points with the official v3 range weights, never UTF-16 length.
    """
    if not isinstance(text, str) or any(0xD800 <= ord(c) <= 0xDFFF or c in "\ufeff\ufffe\uffff" for c in text):
        raise ValueError("Invalid X text encoding")
    text = unicodedata.normalize("NFC", text)
    spans = list(_urls(text))
    parts, previous = [], 0
    for start, end, _ in spans:
        parts.extend((text[previous:start], "a" * 23))
        previous = end
    parts.append(text[previous:])
    masked = "".join(parts)
    if _DOMAIN.search(masked):
        raise ValueError("Use explicit HTTP(S) links instead of bare domains")
    encoded = masked.encode("utf-16-le")
    units = "".join(chr(int.from_bytes(encoded[i:i+2], "little")) for i in range(0, len(encoded), 2))
    def weight(value):
        normal = value.encode("utf-16-le", "surrogatepass").decode("utf-16-le")
        return sum(1 if ord(c) <= 0x10FF or 0x2000 <= ord(c) <= 0x200D
                   or 0x2010 <= ord(c) <= 0x201F or 0x2032 <= ord(c) <= 0x2037 else 2 for c in normal)
    total, previous = 0, 0
    for match in _EMOJI.finditer(units):
        total += weight(units[previous:match.start()]) + 2
        previous = match.end()
    return total + weight(units[previous:])


def contains_url(text):
    # Pricing errs toward reserving the URL tariff, even for unsupported syntax.
    return bool(_URL.search(text) or _DOMAIN.search(text))
