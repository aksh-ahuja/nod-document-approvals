from django.test import SimpleTestCase, override_settings
from drf_spectacular.validation import validate_schema
from rest_framework.test import APIClient


@override_settings(DEBUG=True, NOD_EMAIL_PROVIDER='console')
class OpenApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def test_public_schema_is_valid_without_database_access(self):
        response = self.client.get('/api/schema/')
        self.assertEqual(response.status_code, 200)
        document = response.json()
        validate_schema(document)
        self.assertEqual(document['servers'], [{'url': '/'}])
        self.assertEqual(len(document['paths']), 20)
        self.assertNotIn('/api/schema/', document['paths'])
        self.assertEqual(
            document['components']['securitySchemes']['cookieAuth']['name'], 'nod_session'
        )
        self.assertEqual(document['paths']['/api/v1/auth/login/']['post']['security'], [{}])
        self.assertEqual(
            document['paths']['/api/v1/submissions/create/']['post']['security'],
            [{'cookieAuth': []}],
        )

    def test_schema_describes_requests_envelopes_and_retries(self):
        document = self.client.get('/api/schema/').json()
        schemas = document['components']['schemas']
        login = schemas['LoginRequest']
        self.assertEqual(set(login['required']), {'email', 'password'})
        self.assertTrue(login['properties']['password']['writeOnly'])
        create = document['paths']['/api/v1/submissions/create/']['post']
        self.assertTrue({'200', '201', '400', '403', '409'}.issubset(create['responses']))
        self.assertEqual(len(create['requestBody']['content']['application/json']['examples']), 2)
        listing = document['paths']['/api/v1/submissions/list/']['get']
        self.assertEqual(
            listing['responses']['200']['content']['application/json']['schema']['$ref'],
            '#/components/schemas/SubmissionPageResponse',
        )
        self.assertEqual(
            set(schemas['SubmissionPage']['properties']), {'results', 'count', 'page', 'pages'}
        )
        self.assertTrue(
            {'scope', 'status', 'search', 'page'}.issubset(
                {parameter['name'] for parameter in listing['parameters']}
            )
        )
        complete = document['paths']['/api/v1/uploads/complete/{id}/']['post']
        self.assertTrue({'200', '202'}.issubset(complete['responses']))
        local = document['paths']['/api/v1/uploads/content/{id}/']['put']
        self.assertIn('201', local['responses'])
        self.assertIn('application/octet-stream', local['requestBody']['content'])

    def test_swagger_initializes_csrf_and_uses_local_assets(self):
        response = self.client.get('/api/docs/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('csrftoken', response.cookies)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertContains(response, '/api/docs/assets/swagger-ui-bundle.js')
        self.assertContains(response, '/api/schema/')
        self.assertNotContains(response, 'cdn.jsdelivr.net')
        for filename in ['swagger-ui-bundle.js', 'swagger-ui.css', 'favicon-32x32.png']:
            asset = self.client.get('/api/docs/assets/' + filename)
            self.assertEqual(asset.status_code, 200)
            self.assertTrue(b''.join(asset.streaming_content))

    def test_asset_route_does_not_expose_arbitrary_files(self):
        self.assertEqual(self.client.get('/api/docs/assets/settings.py').status_code, 404)
        self.assertEqual(self.client.get('/api/docs/assets/../settings.py').status_code, 404)

    def test_docs_does_not_bypass_csrf_on_login(self):
        self.client.get('/api/docs/')
        response = self.client.post(
            '/api/v1/auth/login/', {'email': 'a@example.com', 'password': 'invalid'}, format='json'
        )
        self.assertEqual(response.status_code, 403)
