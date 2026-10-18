from ipaddress import ip_address

from django.conf import settings


class TrustedProxyMiddleware:
    """Accept edge headers only from explicitly configured, private proxy peers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.META.get('REMOTE_ADDR') in settings.NOD_TRUSTED_PROXY_IPS:
            scheme = request.META.get('HTTP_X_FORWARDED_PROTO')
            if scheme in ('http', 'https'):
                request.META['wsgi.url_scheme'] = scheme

            try:
                address = ip_address(request.META.get('HTTP_X_REAL_IP', ''))
            except ValueError:
                pass
            else:
                request.META['REMOTE_ADDR'] = str(address)

        return self.get_response(request)
