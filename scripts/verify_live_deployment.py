#!/usr/bin/env python3
"""Verify an HTTPS deployment with three explicitly provisioned test accounts."""

import argparse
import json
from pathlib import Path
import sys
import time
from urllib.parse import parse_qs, urlsplit
import uuid

import requests

from verify_azure_uploads import samples


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class Client:
    def __init__(self, base, credentials):
        self.base = base
        self.session = requests.Session()
        data = self.get('auth/bootstrap/')
        require(data['demo_enabled'] is False, 'Demo credentials must be disabled')
        self.csrf = data['csrf_token']
        result = self.post('auth/login/', credentials)
        self.csrf = result['csrf_token']
        self.user = result['user']
        cookie = next(cookie for cookie in self.session.cookies if cookie.name == 'nod_session')
        require(
            cookie.secure and cookie.has_nonstandard_attr('HttpOnly'), 'Session cookie security'
        )

    def get(self, path):
        response = self.session.get(self.base + '/api/v1/' + path, timeout=65)
        require(response.status_code == 200, f'GET {path.split("?")[0]}: {response.status_code}')
        return response.json()['data']

    def post(self, path, data, expected=200):
        response = self.session.post(
            self.base + '/api/v1/' + path,
            json=data,
            headers={'X-CSRFToken': self.csrf, 'Origin': self.base},
            timeout=65,
        )
        require(response.status_code == expected, f'POST {path}: {response.status_code}')
        return response.json().get('data')


def verify(base, credentials):
    require(base.startswith('https://'), 'Use the HTTPS production origin')
    clients = [Client(base, credentials[key]) for key in ('owner', 'reviewer', 'other')]
    owner, reviewer, other = clients
    ids = []
    try:
        denied = owner.session.post(
            base + '/api/v1/uploads/create/',
            json={
                'filename': 'csrf.txt',
                'size': 1,
            },
            timeout=30,
        )
        require(denied.status_code == 403, 'Missing CSRF must be rejected')
        for extension, content in samples().items():
            instruction = owner.post(
                'uploads/create/',
                {
                    'filename': f'live-check.{extension}',
                    'size': len(content),
                },
                expected=201,
            )
            url = instruction['upload_url']
            require(parse_qs(urlsplit(url).query).get('sp') == ['c'], 'Create-only upload SAS')
            require(
                'skoid' in parse_qs(urlsplit(url).query), 'Expected managed-identity delegation'
            )
            preflight = requests.options(
                url,
                headers={
                    'Origin': base,
                    'Access-Control-Request-Method': 'PUT',
                    'Access-Control-Request-Headers': 'content-type,x-ms-blob-type',
                },
                timeout=30,
            )
            require(preflight.status_code == 200, 'Production CORS preflight failed')
            require(
                preflight.headers.get('Access-Control-Allow-Origin') == base, 'Exact CORS origin'
            )
            uploaded = requests.put(
                url, data=content, headers={**instruction['headers'], 'Origin': base}, timeout=30
            )
            require(uploaded.status_code == 201, 'Direct Azure upload failed')
            require(
                uploaded.headers.get('Access-Control-Allow-Origin') == base, 'PUT CORS response'
            )
            overwrite = requests.put(url, data=content, headers=instruction['headers'], timeout=30)
            require(overwrite.status_code in (403, 409), 'Upload SAS allowed overwriting')
            upload_id = instruction['upload_id']
            owner.post(f'uploads/complete/{upload_id}/', {}, expected=202)
            for _ in range(30):
                status = owner.get(f'uploads/status/{upload_id}/')['status']
                if status == 'ready':
                    break
                require(status in ('pending', 'validating'), 'Upload validation rejected document')
                time.sleep(1)
            require(status == 'ready', 'Running worker did not complete upload')
            submission = owner.post(
                'submissions/create/',
                {
                    'title': f'Deployment check ({extension})',
                    'upload_id': upload_id,
                    'reviewer_id': reviewer.user['id'],
                    'client_request_id': str(uuid.uuid4()),
                },
                expected=201,
            )
            submission_id = submission['id']
            ids.append(submission_id)
            path = f'submissions/file-link/{submission_id}/'
            link = owner.get(path + '?download=true')
            require(
                parse_qs(urlsplit(link['url']).query).get('sp') == ['r'], 'Read-only download SAS'
            )
            download = requests.get(link['url'], headers={'Origin': base}, timeout=30)
            require(
                download.status_code == 200 and download.content == content, 'Download bytes differ'
            )
            require(
                download.headers.get('Access-Control-Allow-Origin') == base, 'GET CORS response'
            )
            unsigned = requests.get(link['url'].split('?')[0], timeout=30)
            require(
                unsigned.status_code in (401, 403, 404)
                or (
                    unsigned.status_code == 409 and b'PublicAccessNotPermitted' in unsigned.content
                ),
                'Unsigned document is readable',
            )
            preview = reviewer.get(path)
            rendered = requests.get(preview['url'], timeout=65)
            require(rendered.status_code == 200, 'Preview unavailable')
            if extension == 'docx':
                require(rendered.content.startswith(b'%PDF-'), 'DOCX PDF conversion failed')
            else:
                require(rendered.content == content, 'Preview bytes differ')
            denied = other.session.get(base + '/api/v1/' + path, timeout=30)
            require(denied.status_code == 404, 'Unrelated user accessed document')
            reviewer.post(
                f'submissions/decision/{submission_id}/',
                {
                    'decision': 'approved',
                    'note': 'Deployment verification.',
                },
            )
            require(
                owner.get(f'submissions/detail/{submission_id}/')['status'] == 'approved',
                'Submitter did not see reviewer decision',
            )
            print(
                f'PASS {extension}: HTTPS, CORS, direct upload, worker, preview, download, isolation, approval',
                flush=True,
            )
        return ids
    finally:
        for client in clients:
            client.post('auth/logout/', {})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='https://nod.haggle.site')
    parser.add_argument('--credentials', required=True)
    args = parser.parse_args()
    credentials = json.loads(Path(args.credentials).read_text())
    verify(args.url.rstrip('/'), credentials)
    print('Live verification passed. Remove the explicitly provisioned test fixtures afterward.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # requests exception strings can expose bearer URLs; print only our safe diagnostics.
        message = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(f'Live verification failed: {message}', file=sys.stderr)
        sys.exit(1)
