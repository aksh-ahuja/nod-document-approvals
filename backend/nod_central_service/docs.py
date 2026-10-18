"""Same-origin Swagger UI and a fixed allowlist of packaged UI assets."""

from importlib.resources import files

from django.http import FileResponse, Http404
from django.shortcuts import render
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET


@require_GET
@never_cache
@ensure_csrf_cookie
def swagger_ui(request):
    return render(request, 'nod/swagger.html')


@require_GET
@cache_control(public=True, max_age=86400)
def swagger_asset(request, name):
    allowed = {
        'swagger-ui-bundle.js': 'text/javascript',
        'swagger-ui.css': 'text/css',
        'favicon-32x32.png': 'image/png',
    }
    if name not in allowed:
        raise Http404
    asset = files('drf_spectacular_sidecar').joinpath(
        'static', 'drf_spectacular_sidecar', 'swagger-ui-dist', name
    )
    return FileResponse(asset.open('rb'), content_type=allowed[name])
