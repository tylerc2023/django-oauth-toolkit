from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.test.utils import modify_settings, override_settings
from django.utils.timezone import now, timedelta

from oauth2_provider.backends import OAuth2Backend
from oauth2_provider.middleware import OAuth2TokenMiddleware
from oauth2_provider.models import get_access_token_model, get_application_model


UserModel = get_user_model()
ApplicationModel = get_application_model()
AccessTokenModel = get_access_token_model()


class BaseTest(TestCase):
    """
    Base class for cases in this module
    """

    def setUp(self):
        self.user = UserModel.objects.create_user("user", "test@example.com", "123456")
        self.app = ApplicationModel.objects.create(
            name="app",
            client_type=ApplicationModel.CLIENT_CONFIDENTIAL,
            authorization_grant_type=ApplicationModel.GRANT_CLIENT_CREDENTIALS,
            user=self.user,
        )
        self.token = AccessTokenModel.objects.create(
            user=self.user, token="tokstr", application=self.app, expires=now() + timedelta(days=365)
        )
        self.factory = RequestFactory()

    def tearDown(self):
        self.user.delete()
        self.app.delete()
        self.token.delete()


class TestOAuth2Backend(BaseTest):
    def test_authenticate(self):
        auth_headers = {
            "HTTP_AUTHORIZATION": "Bearer " + "tokstr",
        }
        request = self.factory.get("/a-resource", **auth_headers)

        backend = OAuth2Backend()
        credentials = {"request": request}
        u = backend.authenticate(**credentials)
        self.assertEqual(u, self.user)

    def test_authenticate_fail(self):
        auth_headers = {
            "HTTP_AUTHORIZATION": "Bearer " + "badstring",
        }
        request = self.factory.get("/a-resource", **auth_headers)

        backend = OAuth2Backend()
        credentials = {"request": request}
        self.assertIsNone(backend.authenticate(**credentials))

        credentials = {"username": "u", "password": "p"}
        self.assertIsNone(backend.authenticate(**credentials))

    def test_get_user(self):
        backend = OAuth2Backend()
        self.assertEqual(self.user, backend.get_user(self.user.pk))
        self.assertIsNone(backend.get_user(123456))


@override_settings(
    AUTHENTICATION_BACKENDS=(
        "oauth2_provider.backends.OAuth2Backend",
        "django.contrib.auth.backends.ModelBackend",
    ),
)
@modify_settings(
    MIDDLEWARE={
        "append": "oauth2_provider.middleware.OAuth2TokenMiddleware",
    }
)
class TestOAuth2Middleware(BaseTest):
    def setUp(self):
        super().setUp()
        self.anon_user = AnonymousUser()

    def dummy_get_response(request):
        return None

    def test_middleware_wrong_headers(self):
        m = OAuth2TokenMiddleware(self.dummy_get_response)
        request = self.factory.get("/a-resource")
        self.assertIsNone(m.process_request(request))
        auth_headers = {
            "HTTP_AUTHORIZATION": "Beerer " + "badstring",  # a Beer token for you!
        }
        request = self.factory.get("/a-resource", **auth_headers)
        self.assertIsNone(m.process_request(request))

    def test_middleware_user_is_set(self):
        m = OAuth2TokenMiddleware(self.dummy_get_response)
        auth_headers = {
            "HTTP_AUTHORIZATION": "Bearer " + "tokstr",
        }
        request = self.factory.get("/a-resource", **auth_headers)
        request.user = self.user
        self.assertIsNone(m.process_request(request))
        request.user = self.anon_user
        self.assertIsNone(m.process_request(request))

    def test_middleware_success(self):
        m = OAuth2TokenMiddleware(self.dummy_get_response)
        auth_headers = {
            "HTTP_AUTHORIZATION": "Bearer " + "tokstr",
        }
        request = self.factory.get("/a-resource", **auth_headers)
        m.process_request(request)
        self.assertEqual(request.user, self.user)

    def test_middleware_response(self):
        m = OAuth2TokenMiddleware(self.dummy_get_response)
        auth_headers = {
            "HTTP_AUTHORIZATION": "Bearer " + "tokstr",
        }
        request = self.factory.get("/a-resource", **auth_headers)
        response = HttpResponse()
        processed = m.process_response(request, response)
        self.assertIs(response, processed)

    def test_middleware_response_header(self):
        m = OAuth2TokenMiddleware(self.dummy_get_response)
        auth_headers = {
            "HTTP_AUTHORIZATION": "Bearer " + "tokstr",
        }
        request = self.factory.get("/a-resource", **auth_headers)
        response = HttpResponse()
        m.process_response(request, response)
        self.assertIn("Vary", response)
        self.assertIn("Authorization", response["Vary"])
