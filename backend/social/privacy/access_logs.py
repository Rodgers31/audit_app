"""Strip private social query capabilities before Uvicorn access formatting."""
import logging

from ..http_policy import private_social_path, social_log_path


class PrivateSocialAccessFilter(logging.Filter):
    def filter(self, record):
        # This is Uvicorn's access emitter contract, not arbitrary log parsing.
        # Unknown formats cannot safely be reflected through its formatter.
        if (record.msg != '%s - "%s %s HTTP/%s" %d'
                or type(record.args) is not tuple or len(record.args) != 5
                or type(record.args[2]) is not str):
            logging.getLogger('social.privacy').warning('Access log format unavailable; private access record omitted.')
            return False
        client, method, target, version, status = record.args
        path = target.partition('?')[0]
        if private_social_path(path):
            record.args = client, method, social_log_path(path), version, status
        return True


def install_private_access_filter():
    logger = logging.getLogger('uvicorn.access')
    if not any(isinstance(item, PrivateSocialAccessFilter) for item in logger.filters):
        logger.addFilter(PrivateSocialAccessFilter())
