"""Validate same-origin JSON commands at the HTTP boundary."""
from urllib.parse import urlsplit

from backend.core.errors import DomainError


def check_origin(request):
    if request.method in {'GET', 'HEAD', 'OPTIONS'} or not request.url.path.startswith('/api/'):
        return
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise DomainError('origin_rejected', 'Use this app from its own origin.', 403)
    origin = request.headers.get('origin')
    if origin:
        parsed = urlsplit(origin)
        if (parsed.scheme, parsed.netloc) != (request.url.scheme, request.url.netloc):
            raise DomainError('origin_rejected', 'Use this app from its own origin.', 403)
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise DomainError('json_required', 'Send an application/json request.', 415)
