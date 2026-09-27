"""A citation's institution and PDF page are evidence, not geographic labels."""
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def extraction_payload(raw):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def page_number(value):
    if type(value) is int:
        return value if value > 0 else None
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"\s*(?:(?:pp?\.?|pages?)\s*)?([0-9]+)(?:\s*[-–]\s*([0-9]+))?\s*", value, re.I
    )
    if not match:
        return None
    try:
        start = int(match[1])
        if start < 1 or (match[2] and int(match[2]) < start):
            return None
    except ValueError:
        return None
    return start


def report_page_url(url, page_ref):
    if not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url.strip())
        if parts.scheme not in ("https", "http") or not parts.hostname:
            return None
    except ValueError:
        return None
    page = page_number(page_ref)
    if page is None or not parts.path.lower().endswith(".pdf"):
        return url.strip()
    fragment = [(k, v) for k, v in parse_qsl(parts.fragment) if k.lower() != "page"]
    fragment.append(("page", str(page)))
    return urlunsplit(parts._replace(fragment=urlencode(fragment)))


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
    if len({n.casefold() for n in role_names}) > 1:
        return None
    for name in role_names:
        for role in re.findall(r"\bcounty\s+(assembly|executive)\b", name, re.I):
            kinds.add("assemblies" if role.lower() == "assembly" else "executives")
    if len(kinds) > 1:
        return None
    if role_names:
        return role_names[0]
    # An explicit volume declaration supplies institution type, not a guess
    # from severity, a finding's subject or a county's geographic association.
    if kinds:
        role = "Assembly" if "assemblies" in kinds else "Executive"
        county = re.sub(r"\s+County$", "", county_name, flags=re.I)
        return f"County {role} of {county}"
    return None
