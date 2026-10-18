import logging

from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def get_success_response(data=None, message=None):
    result = {'status': True}

    if data is not None:
        result['data'] = data

    if message:
        result['message'] = message

    return result


def get_error_response(message, errors=None):
    result = {'status': False, 'message': message}

    if errors is not None:
        result['errors'] = errors

    return result


def service_response(result, data=None):
    if not result.success:
        return Response(get_error_response(result.message), status=result.status_code)

    return Response(
        get_success_response(result.data if data is None else data, result.message),
        status=result.status_code,
    )


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        logger.exception('Unhandled API failure', exc_info=exc)

        return Response(get_error_response('Something went wrong. Please try again.'), status=500)

    message = (
        response.data.get('detail', 'Please check the highlighted fields.')
        if isinstance(response.data, dict)
        else 'Invalid request.'
    )
    response.data = get_error_response(str(message), response.data)

    return response


def csrf_failure(request, reason=''):
    return JsonResponse(
        get_error_response('Your session needs a refresh. Reload and try again.'), status=403
    )
