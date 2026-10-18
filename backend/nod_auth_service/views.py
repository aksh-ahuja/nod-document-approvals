from drf_spectacular.utils import extend_schema_view
from nod_central_service import api_schema as schema

from django.conf import settings
from django.contrib.auth import login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from utils.decorator import validate_input_data
from utils.helpers import get_success_response, service_response

from .serializers import (
    RegistrationSerializer,
    LoginSerializer,
    VerifySerializer,
    ResendSerializer,
    UserSerializer,
)
from .services import GenericAuthService


@extend_schema_view(
    get=schema.operation(
        'auth_bootstrap', 'Authentication', 'Start a browser session', schema.BOOTSTRAP
    )
)
class BootstrapView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(
            get_success_response(
                {'csrf_token': get_token(request), 'demo_enabled': settings.NOD_ENABLE_DEMO}
            )
        )


@method_decorator(csrf_protect, name='dispatch')
@extend_schema_view(
    post=schema.operation(
        'auth_register',
        'Authentication',
        'Register and send an email code',
        schema.CHALLENGE,
        request=RegistrationSerializer,
        code=202,
        errors=(400, 403, 409, 429, 503),
        description='Use a real email address on production. Codes expire after 10 minutes. This sends a real email; console OTPs are used only locally.',
        examples=[
            schema.example(
                'Register',
                {
                    'name': 'Taylor',
                    'email': 'you@example.com',
                    'password': 'Replace-with-your-own-password!',
                },
            )
        ],
    )
)
class RegistrationView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @validate_input_data(RegistrationSerializer)
    def post(self, request, validated_data):
        result = GenericAuthService.register(
            validated_data['name'],
            validated_data['email'],
            validated_data['password'],
            request.META.get('REMOTE_ADDR', ''),
        )

        return service_response(result)


@method_decorator(csrf_protect, name='dispatch')
@extend_schema_view(
    post=schema.operation(
        'auth_verify',
        'Authentication',
        'Verify email and sign in',
        schema.AUTH,
        request=VerifySerializer,
        code=201,
        errors=(400, 403, 409, 429),
        description='Use the challenge_id from registration and the six-digit code from your email. The session and CSRF cookie rotate on success.',
    )
)
class VerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @validate_input_data(VerifySerializer)
    def post(self, request, validated_data):
        result = GenericAuthService.verify(
            validated_data['challenge_id'],
            validated_data['code'],
            request.META.get('REMOTE_ADDR', ''),
        )

        if not result.success:
            return service_response(result)

        login(request, result.data, backend='django.contrib.auth.backends.ModelBackend')

        return service_response(
            result, {'user': UserSerializer(result.data).data, 'csrf_token': get_token(request)}
        )


@method_decorator(csrf_protect, name='dispatch')
@extend_schema_view(
    post=schema.operation(
        'auth_resend',
        'Authentication',
        'Resend the verification code',
        schema.CHALLENGE,
        request=ResendSerializer,
        code=202,
        errors=(400, 403, 429, 503),
        description='Wait 60 seconds between sends. Use the new challenge_id returned by this request.',
    )
)
class ResendView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @validate_input_data(ResendSerializer)
    def post(self, request, validated_data):
        return service_response(
            GenericAuthService.resend(
                validated_data['challenge_id'], request.META.get('REMOTE_ADDR', '')
            )
        )


@method_decorator(csrf_protect, name='dispatch')
@extend_schema_view(
    post=schema.operation(
        'auth_login',
        'Authentication',
        'Sign in for Try it out',
        schema.AUTH,
        request=LoginSerializer,
        errors=(400, 401, 403, 429),
        description='Execute this endpoint before protected requests. Cookies and CSRF updates are automatic in this Swagger UI. Demo credentials work only locally; use your registered account on production.',
        examples=[
            schema.example(
                'Local demo only', {'email': 'jamie@nod.demo', 'password': 'NodDemo!2026'}
            )
        ],
    )
)
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @validate_input_data(LoginSerializer)
    def post(self, request, validated_data):
        result = GenericAuthService.login(
            validated_data['email'], validated_data['password'], request.META.get('REMOTE_ADDR', '')
        )

        if not result.success:
            return service_response(result)

        login(request, result.data, backend='django.contrib.auth.backends.ModelBackend')

        return service_response(
            result, {'user': UserSerializer(result.data).data, 'csrf_token': get_token(request)}
        )


@extend_schema_view(
    post=schema.operation(
        'auth_logout', 'Authentication', 'Sign out', schema.MESSAGE, errors=(403,)
    )
)
class LogoutView(APIView):
    def post(self, request):
        logout(request)

        return Response(get_success_response(message='You are signed out.'))


@extend_schema_view(
    get=schema.operation(
        'auth_me', 'Authentication', 'Read the signed-in user', schema.USER, errors=(403,)
    )
)
class MeView(APIView):
    def get(self, request):
        return Response(get_success_response(UserSerializer(request.user).data))


@extend_schema_view(
    get=schema.operation(
        'reviewers_list',
        'Submissions',
        'Find eligible reviewers',
        schema.USERS,
        errors=(403,),
        description='Copy an id from data into reviewer_id when creating a submission. Self-review is excluded.',
    )
)
class ReviewersView(APIView):
    def get(self, request):
        users = (
            GenericAuthService.get_users(can_review=True)
            .exclude(pk=request.user.pk)
            .order_by('name')
        )

        return Response(get_success_response(UserSerializer(users, many=True).data))
