#!/usr/bin/env python3
"""Exercise Nod's real Azure transfers using a temporary local database.

Run with .venv/bin/python scripts/verify_azure_uploads.py. Loads .env without
executing shell code. Creates synthetic blobs and deletes only those blobs.
Never prints signed URLs, credentials, or document contents.
"""

import io
import logging
import os
from pathlib import Path
import secrets
import shlex
import sys
import tempfile
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
import uuid
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
ORIGINS = ['http://localhost:5173', 'http://127.0.0.1:5173']


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def transfer(url, method='GET', content=None, headers=None):
    request = Request(url, data=content, method=method, headers=headers or {})

    try:
        response = urlopen(request, timeout=30)
    except HTTPError as error:
        response = error

    with response:
        return response.status, response.headers, response.read()


def samples():
    document = io.BytesIO()

    with ZipFile(document, 'w') as archive:
        archive.writestr(
            '_rels/.rels',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        archive.writestr(
            '[Content_Types].xml',
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        archive.writestr(
            'word/document.xml',
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Nod Azure smoke test.</w:t></w:r></w:p></w:body></w:document>',
        )

    return {
        'txt': b'Nod Azure smoke test. Synthetic document.\n',
        'pdf': sample_pdf(),
        'docx': document.getvalue(),
    }


def sample_pdf():
    stream = b'BT /F1 18 Tf 72 720 Td (Nod deployment verification) Tj ET\n'
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'endstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    data = b'%PDF-1.4\n'
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(data)
    data += b'xref\n0 6\n0000000000 65535 f \n'
    data += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    data += f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    return data


def require_private(url):
    status, _, body = transfer(url.split('?')[0])
    blocked = status in (401, 403, 404) or (
        status == 409 and b'<Code>PublicAccessNotPermitted</Code>' in body
    )
    require(blocked, f'Unexpected unsigned-read status: {status}')


def verify():
    import django

    django.setup()
    logging.disable(logging.CRITICAL)

    from django.core.management import call_command
    from rest_framework.test import APIClient

    from nod_auth_service.models import User
    from nod_upload_service.models import DocumentUpload
    from nod_upload_service.services.generic_upload_worker_service import (
        GenericUploadWorkerService,
    )
    from utils.storage.factory import get_document_storage

    call_command('migrate', verbosity=0, interactive=False)
    password = secrets.token_urlsafe(32)
    owner = User.objects.create_user(
        'azure-smoke-owner@nod.invalid', password=password, name='Azure smoke', email_verified=True
    )
    reviewer = User.objects.create_user(
        'azure-smoke-reviewer@nod.invalid',
        name='Azure reviewer',
        email_verified=True,
        can_review=True,
    )
    other = User.objects.create_user(
        'azure-smoke-other@nod.invalid', name='Unrelated user', email_verified=True
    )
    client = APIClient(enforce_csrf_checks=True, HTTP_HOST='localhost')
    token = client.get('/api/v1/auth/bootstrap/').data['data']['csrf_token']
    login = client.post(
        '/api/v1/auth/login/',
        {'email': owner.email, 'password': password},
        format='json',
        HTTP_X_CSRFTOKEN=token,
    )
    require(login.status_code == 200, 'Local session login failed')
    client.credentials(HTTP_X_CSRFTOKEN=login.data['data']['csrf_token'])
    storage = get_document_storage()

    try:
        for extension, content in samples().items():
            intent = client.post(
                '/api/v1/uploads/create/',
                {
                    'filename': f'azure-smoke.{extension}',
                    'size': len(content),
                },
                format='json',
            )
            require(
                intent.status_code == 201,
                f'{extension}: upload signing failed ({intent.status_code})',
            )
            instruction = intent.data['data']
            url = instruction['upload_url']
            query = parse_qs(urlsplit(url).query)
            require(
                query.get('sp') == ['c'] and 'skoid' in query,
                'Expected create-only user-delegation SAS',
            )

            for origin in ORIGINS:
                status, headers, _ = transfer(
                    url,
                    'OPTIONS',
                    headers={
                        'Origin': origin,
                        'Access-Control-Request-Method': 'PUT',
                        'Access-Control-Request-Headers': 'content-type,x-ms-blob-type',
                    },
                )
                require(
                    status == 200 and headers.get('Access-Control-Allow-Origin') == origin,
                    'Allowed-origin preflight failed',
                )

            status, headers, _ = transfer(
                url,
                'OPTIONS',
                headers={
                    'Origin': 'https://untrusted.invalid',
                    'Access-Control-Request-Method': 'PUT',
                    'Access-Control-Request-Headers': 'content-type,x-ms-blob-type',
                },
            )
            require(
                status == 403 and not headers.get('Access-Control-Allow-Origin'),
                'Unlisted-origin preflight must fail',
            )
            headers = {**instruction['headers'], 'Origin': ORIGINS[0]}
            status, response_headers, _ = transfer(url, 'PUT', content, headers)
            require(status == 201 and response_headers.get('ETag'), 'Azure PUT failed')
            require(
                response_headers.get('Access-Control-Allow-Origin') == ORIGINS[0],
                'PUT response missing CORS header',
            )
            status, _, _ = transfer(url, 'PUT', content, headers)
            require(status in (403, 409), 'Create-only URL unexpectedly allowed overwrite')
            require_private(url)

            upload_id = instruction['upload_id']
            completed = client.post(f'/api/v1/uploads/complete/{upload_id}/')
            require(completed.status_code == 202, 'Upload completion failed')
            require(GenericUploadWorkerService.run_once(), 'Worker did not claim upload')
            upload = DocumentUpload.objects.get(public_id=upload_id)
            require(upload.status == 'ready', f'{extension}: worker did not validate upload')
            submission = client.post(
                '/api/v1/submissions/create/',
                {
                    'title': 'Azure integration smoke test',
                    'reviewer_id': str(reviewer.public_id),
                    'client_request_id': str(uuid.uuid4()),
                    'upload_id': upload_id,
                },
                format='json',
            )
            require(submission.status_code == 201, 'Validated upload attachment failed')
            path = f'/api/v1/submissions/file-link/{submission.data["data"]["id"]}/'
            link = client.get(path + '?download=true')
            require(link.status_code == 200, 'Download signing failed')
            read_url = link.data['data']['url']
            require(
                parse_qs(urlsplit(read_url).query).get('sp') == ['r'], 'Download SAS not read-only'
            )
            status, headers, downloaded = transfer(read_url, headers={'Origin': ORIGINS[0]})
            require(status == 200 and downloaded == content, 'Downloaded bytes differ')
            require(
                'attachment' in headers.get('Content-Disposition', ''),
                'Missing download disposition',
            )
            require(headers.get('Access-Control-Allow-Origin') == ORIGINS[0], 'GET CORS failed')
            require(transfer(read_url, 'HEAD')[0] == 200, 'Signed HEAD failed')
            require_private(read_url)
            if extension != 'docx':
                preview = client.get(path)
                require(preview.status_code == 200, 'Inline preview signing failed')
                require(transfer(preview.data['data']['url'])[2] == content, 'Inline bytes differ')
            outsider = APIClient(HTTP_HOST='localhost')
            outsider.force_login(other)
            require(outsider.get(path).status_code == 404, 'Unrelated user obtained a link')
            print(
                f'PASS {extension}: delegated SAS, CORS, private PUT, validation, attachment, download, isolation'
            )
    finally:
        for upload in DocumentUpload.objects.all():
            for key in (upload.staging_key, upload.final_key):
                if key:
                    storage.delete(key)
        print('Synthetic staging and final blobs cleaned up.')


def main():
    for token in shlex.split((ROOT / '.env').read_text(), comments=True):
        if '=' in token:
            key, value = token.split('=', 1)
            os.environ[key] = value

    require(os.getenv('NOD_STORAGE_PROVIDER') == 'azure', 'Configure Azure storage in .env first')
    sys.path.insert(0, str(ROOT / 'backend'))
    with tempfile.TemporaryDirectory(prefix='nod-azure-smoke-') as directory:
        os.environ.update(
            {
                'DJANGO_SETTINGS_MODULE': 'nod_central_service.settings',
                'NOD_DEBUG': 'true',
                'NOD_DB_ENGINE': 'sqlite',
                'NOD_SQLITE_PATH': str(Path(directory) / 'smoke.sqlite3'),
                'NOD_ALLOWED_HOSTS': 'localhost',
                'NOD_COOKIE_SECURE': 'false',
            }
        )
        verify()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # SDK exception strings may contain signed URLs; never print those.
        message = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(f'Azure verification failed: {message}', file=sys.stderr)
        sys.exit(1)
