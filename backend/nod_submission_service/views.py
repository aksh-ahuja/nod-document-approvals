from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from nod_central_service import api_schema as schema

from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.parsers import JSONParser
from rest_framework.views import APIView
from django.http import FileResponse

from utils.decorator import validate_input_data
from utils.helpers import get_success_response, service_response

from .serializers import (
    CreateSubmissionSerializer,
    DecisionSerializer,
    SubmissionQuerySerializer,
    SubmissionSerializer,
    SubmissionDetailSerializer,
    SubmissionEventSerializer,
)
from .services import GenericSubmissionService
from .messages import FailureMessage


@extend_schema_view(
    post=schema.operation(
        'submissions_create',
        'Submissions',
        'Submit text or a validated file',
        schema.SUBMISSION,
        request=CreateSubmissionSerializer,
        code=201,
        also_codes=(200,),
        errors=(400, 403, 409, 410),
        description='Supply exactly one of content or upload_id. Get reviewer_id from reviewers/list/. Use a fresh UUID client_request_id for a new submission. An identical retry returns the original submission with 200; different content with the same key returns 409.',
        examples=[
            schema.example(
                'Write text',
                {
                    'title': 'Launch plan',
                    'content': 'Please review this launch plan.',
                    'reviewer_id': '22222222-2222-4222-8222-222222222222',
                    'client_request_id': '33333333-3333-4333-8333-333333333333',
                },
            ),
            schema.example(
                'Attach a ready upload',
                {
                    'title': 'Uploaded plan',
                    'upload_id': '11111111-1111-4111-8111-111111111111',
                    'reviewer_id': '22222222-2222-4222-8222-222222222222',
                    'client_request_id': '44444444-4444-4444-8444-444444444444',
                },
            ),
        ],
    )
)
class CreateSubmissionView(APIView):
    parser_classes = [JSONParser]

    @validate_input_data(CreateSubmissionSerializer)
    def post(self, request, validated_data):
        result = GenericSubmissionService.create_submission(
            request.user,
            validated_data['title'],
            validated_data['content'],
            validated_data['reviewer_id'],
            validated_data['client_request_id'],
            upload_id=validated_data.get('upload_id'),
        )

        return service_response(
            result, SubmissionDetailSerializer(result.data).data if result.success else None
        )


@extend_schema_view(
    get=schema.operation(
        'submissions_list',
        'Submissions',
        'List your submitted or assigned documents',
        schema.SUBMISSIONS,
        parameters=[SubmissionQuerySerializer, OpenApiParameter('page', int)],
        errors=(400, 403, 404),
    )
)
class SubmissionListView(ListAPIView):
    serializer_class = SubmissionSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            from .models import Submission

            return Submission.objects.none()
        query = SubmissionQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data

        if data['scope'] == 'assigned' and not self.request.user.can_review:
            raise PermissionDenied('Reviewer access is required.')

        return GenericSubmissionService.get_submissions(
            self.request.user,
            scope=data['scope'],
            status=data.get('status'),
            search=data.get('search'),
        )


@extend_schema_view(
    get=schema.operation(
        'submissions_detail',
        'Submissions',
        'Read a submission',
        schema.SUBMISSION,
        errors=(403, 404),
    )
)
class SubmissionDetailView(APIView):
    def get(self, request, id):
        submission = GenericSubmissionService.get_detail(request.user, id)

        if submission is None:
            raise NotFound(FailureMessage.NOT_FOUND)

        return Response(get_success_response(SubmissionDetailSerializer(submission).data))


@extend_schema_view(
    post=schema.operation(
        'submissions_decision',
        'Submissions',
        'Approve or reject an assigned submission',
        schema.SUBMISSION,
        request=DecisionSerializer,
        errors=(400, 403, 404, 409),
        description='Sign in as the assigned reviewer. Rejection requires non-blank feedback. Decisions are final. Identical retries are safe; conflicting decisions return 409.',
        examples=[
            schema.example('Approve', {'decision': 'approved', 'note': 'Ready to launch.'}),
            schema.example(
                'Reject', {'decision': 'rejected', 'note': 'Please add the cost breakdown.'}
            ),
        ],
    )
)
class DecisionView(APIView):
    @validate_input_data(DecisionSerializer)
    def post(self, request, id, validated_data):
        result = GenericSubmissionService.decide(
            request.user, id, validated_data['decision'], validated_data['note']
        )

        return service_response(
            result, SubmissionDetailSerializer(result.data).data if result.success else None
        )


@extend_schema_view(
    get=schema.operation(
        'submissions_history',
        'Submissions',
        'Read the decision timeline',
        schema.HISTORY,
        errors=(403, 404),
    )
)
class HistoryView(APIView):
    def get(self, request, id):
        submission = GenericSubmissionService.get_detail(request.user, id)

        if submission is None:
            raise NotFound(FailureMessage.NOT_FOUND)

        history = GenericSubmissionService.get_history(submission)

        return Response(get_success_response(SubmissionEventSerializer(history, many=True).data))


@extend_schema_view(
    get=schema.operation(
        'submissions_summary',
        'Submissions',
        'Read dashboard counts',
        schema.SUMMARY,
        parameters=[schema.SCOPE],
        errors=(400, 403),
    )
)
class SummaryView(APIView):
    def get(self, request):
        query = SubmissionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        scope = query.validated_data['scope']

        if scope == 'assigned' and not request.user.can_review:
            raise PermissionDenied('Reviewer access is required.')

        return Response(get_success_response(GenericSubmissionService.summary(request.user, scope)))


@extend_schema_view(
    get=schema.operation(
        'submissions_file_link',
        'Submissions',
        'Get a private preview or download link',
        schema.FILE_LINK,
        parameters=[OpenApiParameter('download', bool, default=False)],
        errors=(403, 404, 503),
        description='Use download=true for original bytes; otherwise DOCX is converted to PDF. Open the returned URL to view the file. Links expire after five minutes.',
    )
)
class FileLinkView(APIView):
    def get(self, request, id):
        result = GenericSubmissionService.get_file_link(
            request.user, id, download=request.query_params.get('download') == 'true'
        )
        response = service_response(result)
        response['Cache-Control'] = 'private, no-store'
        response['Referrer-Policy'] = 'no-referrer'

        return response


@extend_schema_view(
    get=extend_schema(
        operation_id='submissions_local_content',
        tags=['Local file transfer'],
        summary='Read signed file bytes (local development only)',
        parameters=[schema.TOKEN],
        responses={
            (200, 'application/octet-stream'): {'type': 'string', 'format': 'binary'},
            403: schema.ERROR,
            404: schema.ERROR,
        },
        description='Follow the URL returned by file-link on the local storage provider. Production returns Azure URLs instead.',
    )
)
class LocalFileView(APIView):
    def get(self, request, id):
        result = GenericSubmissionService.get_local_file(
            request.user, id, request.query_params.get('token', '')
        )

        if not result.success:
            return service_response(result)

        data = result.data
        response = FileResponse(
            data['file'],
            as_attachment=data['download'],
            filename=data['filename'],
            content_type=data['content_type'],
        )
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'SAMEORIGIN'
        response['Referrer-Policy'] = 'no-referrer'

        return response
