from drf_spectacular.utils import extend_schema_view
from nod_central_service import api_schema as schema

from rest_framework.views import APIView

from utils.decorator import validate_input_data
from utils.helpers import service_response

from .services.generic_upload_service import GenericUploadService
from .serializers import CreateUploadSerializer


class PrivateUploadView(APIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        response['Referrer-Policy'] = 'no-referrer'

        return response


@extend_schema_view(
    post=schema.operation(
        'uploads_create',
        'Uploads',
        'Get a private upload URL',
        schema.UPLOAD,
        request=CreateUploadSerializer,
        code=201,
        errors=(400, 403, 429, 503),
        description='PDF, DOCX or TXT, at most 10 MB. PUT raw file bytes to upload_url with the returned headers, then call complete. The signed URL expires in five minutes. Cloud PUT uses no Nod cookies or CSRF headers.',
        examples=[
            schema.example(
                'Text file', {'filename': 'review.txt', 'size': 25, 'content_type': 'text/plain'}
            )
        ],
    )
)
class CreateUploadView(PrivateUploadView):
    @validate_input_data(CreateUploadSerializer)
    def post(self, request, validated_data):
        return service_response(
            GenericUploadService.create(
                request.user, validated_data['filename'], validated_data['size']
            )
        )


@extend_schema_view(
    post=schema.operation(
        'uploads_complete',
        'Uploads',
        'Queue an uploaded file for validation',
        schema.UPLOAD_STATE,
        code=202,
        also_codes=(200,),
        errors=(400, 403, 404, 409, 410, 503),
        description='After transferring the bytes, use upload_id as id. Poll status until ready before attaching to a submission.',
    )
)
class CompleteUploadView(PrivateUploadView):
    def post(self, request, id):
        return service_response(GenericUploadService.complete(request.user, id))


@extend_schema_view(
    get=schema.operation(
        'uploads_status',
        'Uploads',
        'Check upload validation',
        schema.UPLOAD_STATE,
        errors=(403, 404),
    )
)
class UploadStatusView(PrivateUploadView):
    def get(self, request, id):
        return service_response(GenericUploadService.status(request.user, id))


@extend_schema_view(
    put=schema.operation(
        'uploads_local_content',
        'Local file transfer',
        'Transfer file bytes (local development only)',
        schema.MESSAGE,
        code=201,
        request={'application/octet-stream': {'type': 'string', 'format': 'binary'}},
        parameters=[schema.TOKEN],
        errors=(400, 403, 404, 409, 410),
        description='Only for the local storage provider. Copy id and token from the upload_url. In Azure production, upload directly to the returned Blob URL instead.',
    )
)
class LocalUploadView(PrivateUploadView):
    def put(self, request, id):
        length = request.META.get('CONTENT_LENGTH', '')
        size = int(length) if length.isdigit() else 0

        return service_response(
            GenericUploadService.receive_local(
                request.user, id, request.query_params.get('token', ''), request.stream, size
            )
        )
