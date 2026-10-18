from drf_spectacular.views import SpectacularJSONAPIView

from .docs import swagger_ui, swagger_asset
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path

from nod_auth_service.views import ReviewersView


def health(request):
    return JsonResponse({'status': True, 'service': 'nod-api'})


def readiness(request):
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')

    return JsonResponse({'status': True})


urlpatterns = [
    path('api/docs/', swagger_ui, name='nod-swagger'),
    path('api/docs/assets/<str:name>', swagger_asset, name='nod-swagger-asset'),
    path('api/schema/', SpectacularJSONAPIView.as_view(), name='nod-openapi'),
    path('api/v1/auth/', include('nod_auth_service.urls')),
    path('api/v1/uploads/', include('nod_upload_service.urls')),
    path('api/v1/submissions/', include('nod_submission_service.urls')),
    path('api/v1/reviewers/list/', ReviewersView.as_view()),
    path('api/health/', health),
    path('api/ready/', readiness),
]
