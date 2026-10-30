"""Site-first publication policy, independent of adapters and editorial versions."""
import re
from urllib.parse import urlsplit

HOME = 'https://www.auditgava.com'
_URL_START = re.compile(r'https?://|www\.', re.I)
_DOMAIN = re.compile(r'(?<![\w@])(?:[a-z0-9][a-z0-9-]{0,62}\.){1,10}[a-z]{2,63}(?::[0-9]+)?(?:[/?:#][^\s<>]*)?', re.I)


def on_site(value):
    if type(value) is not str or not value or any(c.isspace() or ord(c) < 32 or c == '\\' for c in value):
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == 'https' and url.hostname in {'auditgava.com', 'www.auditgava.com'}
                and url.username is None and url.password is None and url.port in (None, 443))
    except (ValueError, TypeError):
        return False


def caption_urls(text):
    """Explicit and common bare URLs, without treating email as a destination."""
    if type(text) is not str:
        return ()
    # Adjacent links can be separated by punctuation without whitespace. Every
    # explicit URL start must be inspected; one onsite path cannot mask another.
    starts = [m.start() for m in _URL_START.finditer(text)
        if not (m.group().lower() == 'www.' and text[max(0,m.start()-3):m.start()] == '://')]
    values, masked = [], list(text)
    for index, start in enumerate(starts):
        end = starts[index+1] if index+1 < len(starts) else len(text)
        token = re.split(r'[\s<>\x00-\x20]', text[start:end], maxsplit=1)[0]
        values.append(token.rstrip('.,;!?)'))
        masked[start:start+len(token)] = ' ' * len(token)
    values.extend(m.group().rstrip('.,;!?)') for m in _DOMAIN.finditer(''.join(masked)))
    return tuple(value if '://' in value else 'https://'+value for value in values)


def publication_destination_problem(link, text):
    """Returns a stable refusal code, never follows links or changes content."""
    urls = caption_urls(text)
    if link is not None and not on_site(link):
        return 'AUDITGAVA_DESTINATION_REQUIRED'
    if any(not on_site(value) for value in urls):
        return 'EXTERNAL_CAPTION_LINK'
    if link is None and not urls:
        return 'AUDITGAVA_DESTINATION_REQUIRED'
    return None


def valid_hashtag(value):
    if type(value) is not str:
        return False
    word = value[1:] if value.startswith('#') else value
    return bool(word) and any(c.isalpha() for c in word) and all(c.isalnum() or c == '_' for c in word)
