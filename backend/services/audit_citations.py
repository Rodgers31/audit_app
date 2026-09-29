"""A citation's institution and PDF page are evidence, not geographic labels."""
import json
import re
from urllib.parse import parse_qsl, unquote_plus, urlencode, urlsplit, urlunsplit

from sqlalchemy import func


# These patterns are also used by the audit publication query. Keep them in
# the common Python/PostgreSQL/SQLite regular-expression subset: SQLAlchemy
# translates regexp_match to PostgreSQL ~ and SQLite's REGEXP function.
_SPACE = r"[ \t\n\r\f\v]"
NUMERIC_LOCATOR_PATTERN = (
    rf"^{_SPACE}*(?:(?:pp?\.?|pages?){_SPACE}*)?"
    rf"([0-9]{{1,9}})(?:{_SPACE}*[-–]{_SPACE}*([0-9]{{1,9}}))?{_SPACE}*$"
)
_ROMAN = r"M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
NAMED_LOCATOR_PATTERN = (
    rf"^{_SPACE}*(?:annex(?:ure)?|appendix|schedule){_SPACE}*"
    rf"(?:[A-Z]|[1-9][0-9]*|(?=[MDCLXVI]){_ROMAN}){_SPACE}*$"
)

# Explicit port ranges prevent SQL from admitting a URL that urlsplit rejects.
_HOST_LABEL = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
_PORT = r"(?:[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])"
_URL_TAIL_CHAR = r"[a-z0-9._~:/?#\[\]@!$&'()*+,;=-]"
SOURCE_URL_PATTERN = (
    rf"^https?://{_HOST_LABEL}(?:\.{_HOST_LABEL})*(?::{_PORT})?"
    rf"(?:[/?#](?:{_URL_TAIL_CHAR}|%[0-9a-f]{{2}})*)?\Z"
)


def safe_source_url(url):
    """Whether a stored source URL is a syntactically safe HTTP(S) link."""
    return isinstance(url, str) and re.fullmatch(
        SOURCE_URL_PATTERN, url, re.I | re.ASCII
    ) is not None


def extraction_payload(raw):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def extraction_json_type(column, dialect):
    """JSON value type for the two database dialects used by the API/tests."""
    if dialect == "postgresql":
        return func.jsonb_typeof(column)
    if dialect == "sqlite":
        return func.json_type(column)
    raise NotImplementedError(f"JSON projection is unsupported for {dialect}")


def string_extraction_payloads(db, rows):
    """Read full JSON only for historical rows stored as serialized strings."""
    from models import Extraction

    ids = {
        row.extraction_id
        for row in rows
        if row.extraction_payload_type in ("string", "text")
    }
    if not ids:
        return {}
    return {
        extraction_id: extraction_payload(raw)
        for extraction_id, raw in db.query(Extraction.id, Extraction.extracted_json)
        .filter(Extraction.id.in_(ids))
        .all()
    }


def page_number(value):
    if type(value) is int:
        return value if value > 0 else None
    if not isinstance(value, str):
        return None
    match = re.fullmatch(NUMERIC_LOCATOR_PATTERN, value, re.I | re.ASCII)
    if not match:
        return None
    try:
        start = int(match[1])
        if start < 1 or (match[2] and int(match[2]) < start):
            return None
    except ValueError:
        return None
    return start


def citation_page(value):
    """A PDF page number or a named report locator, never a malformed page."""
    number = page_number(value)
    if number is not None:
        return number
    if not isinstance(value, str):
        return None
    # Match the SQL policy's ASCII whitespace set exactly. Python's split()
    # also folds Unicode separators, which the SQL expression does not.
    label = re.sub(r"[ \t\n\r\f\v]+", " ", value).strip(" \t\n\r\f\v")
    if re.fullmatch(NAMED_LOCATOR_PATTERN, label, re.I | re.ASCII):
        return label
    return None


def report_page_url(url, page_ref, *, clear_stale_page=False):
    if not safe_source_url(url):
        return None
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("https", "http") or not parts.hostname:
            return None
    except ValueError:
        return None
    page = page_number(page_ref)
    if page is None or not parts.path.lower().endswith(".pdf"):
        if clear_stale_page:
            # Keep unrelated fragment settings verbatim. An inherited #page=N
            # is not evidence of a page for this finding.
            fragment = "&".join(
                part for part in parts.fragment.split("&")
                if unquote_plus(part.partition("=")[0]).casefold() != "page"
            )
            return urlunsplit(parts._replace(fragment=fragment))
        return url
    fragment = [(k, v) for k, v in parse_qsl(parts.fragment) if k.lower() != "page"]
    fragment.append(("page", str(page)))
    return urlunsplit(parts._replace(fragment=urlencode(fragment)))


def _county_role(name, county_name):
    """Resolve the two printed auditee forms against the supplied county."""
    front = re.fullmatch(r"county\s+(assembly|executive)\s+of\s+(.+)", name, re.I)
    back = re.fullmatch(r"(.+?)\s+county\s+(assembly|executive)", name, re.I)
    if front:
        role, county = front.group(1), front.group(2)
    elif back:
        county, role = back.group(1), back.group(2)
    else:
        return None
    normalize = lambda s: re.sub(r"[^a-z0-9]", "", s.casefold())
    expected = normalize(re.sub(r"\s+County$", "", county_name, flags=re.I))
    actual = normalize(county)
    if actual == expected or (expected == "nairobi" and actual == "nairobicity"):
        return role.casefold()
    return None


def audited_institution(raw, *, county_name=None, document_meta=None):
    """Use extracted identity; county affiliation alone never names an auditee.

    County-volume extractors declare assemblies/executives separately. Older
    extractions already retain the full institution in entity_name. Conflicting
    declarations withhold the label, preserving the finding and citation.
    """
    payload = extraction_payload(raw)
    names = [payload.get("entity_name"), payload.get("auditee")]
    names = [
        re.sub(r"\s+", " ", n).strip()
        for n in names
        if isinstance(n, str) and n.strip()
    ]
    if county_name is None:
        return names[0] if names and len({name.casefold() for name in names}) == 1 else None
    doc_meta = document_meta if isinstance(document_meta, dict) else {}
    stats = doc_meta.get("extraction_stats")
    stats = stats if isinstance(stats, dict) else {}
    kinds = {
        v
        for v in (payload.get("volume_kind"), stats.get("volume_kind"))
        if isinstance(v, str) and v in ("assemblies", "executives")
    }
    role_names = [
        n for n in names if re.search(r"\bcounty\s+(assembly|executive)\b", n, re.I)
    ]
    if role_names:
        # Current OAG volumes retain their printed auditee alongside the
        # canonical entity name (Taita/Taveta, Nairobi City, etc.). Every
        # declaration must name THIS county and the SAME role, even if the
        # printed auditee is the only declaration present.
        roles = {_county_role(n, county_name) for n in role_names}
        if None in roles or len(roles) != 1:
            return None
    for name in role_names:
        for role in re.findall(r"\bcounty\s+(assembly|executive)\b", name, re.I):
            kinds.add("assemblies" if role.lower() == "assembly" else "executives")
    if len(kinds) > 1:
        return None
    if role_names:
        printed = payload.get("auditee")
        if isinstance(printed, str) and printed.strip() in role_names:
            return printed.strip()
        return role_names[0]
    # An explicit volume declaration supplies institution type, not a guess
    # from severity, a finding's subject or a county's geographic association.
    if kinds and not names:
        role = "Assembly" if "assemblies" in kinds else "Executive"
        county = re.sub(r"\s+County$", "", county_name, flags=re.I)
        return f"County {role} of {county}"
    return None
