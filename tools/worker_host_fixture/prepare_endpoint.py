"""Generate identical inert JPEG and certificate with the frozen helper."""
from pathlib import Path
import endpoints


def prepared(address, handler):
    if (type(address) is not tuple or len(address) != 2
            or type(address[0]) is not str or address[0] != '127.0.0.4'
            or type(address[1]) is not int or address[1] != 443
            or handler is not endpoints.Endpoint):
        raise RuntimeError('Fixed inert preparation required')
    target = Path('/evidence/endpoint-image.jpg')
    with target.open('xb') as stream:
        stream.write(endpoints.image())
    raise SystemExit(0)


if __name__ == '__main__':
    endpoints.ThreadingHTTPServer = prepared
    endpoints.main('127.0.0.4', prewarm=True)
