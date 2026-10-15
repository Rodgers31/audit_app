"""Bound JSON metadata before FastAPI reads or decodes it; bytes go to R2."""
from fastapi import Request

from ..http_boundary import SocialRoute
from ..service import SocialError


MAX_METADATA_BYTES = 64 * 1024


class MediaRoute(SocialRoute):
    async def prepare_request(self, request: Request):
        lengths = request.headers.getlist('content-length')
        if lengths:
            if (len(lengths) != 1 or not 1 <= len(lengths[0]) <= 10
                    or not lengths[0].isascii() or not lengths[0].isdecimal()):
                raise SocialError('INVALID_REQUEST', 'Use one valid Content-Length header.', 400)
            if int(lengths[0]) > MAX_METADATA_BYTES:
                raise self.too_large()

        buffered = bytearray()
        async for chunk in request.stream():
            if len(buffered) + len(chunk) > MAX_METADATA_BYTES:
                raise self.too_large()
            buffered.extend(chunk)
        body = bytes(buffered)
        pending = True

        async def receive():
            nonlocal pending
            if pending:
                pending = False
                return {'type': 'http.request', 'body': body, 'more_body': False}
            return await request.receive()

        # Keep the same scope/state, including the private request ID, while
        # replaying only the bounded bytes to FastAPI's normal JSON validation.
        return Request(request.scope, receive)

    @staticmethod
    def too_large():
        return SocialError('MEDIA_REQUEST_TOO_LARGE', 'Media metadata must fit within 64 KiB. Upload file bytes directly to private storage.', 413)
