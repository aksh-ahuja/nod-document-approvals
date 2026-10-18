from django.urls import path

from .views import (
    BootstrapView,
    RegistrationView,
    VerifyView,
    ResendView,
    LoginView,
    LogoutView,
    MeView,
)

urlpatterns = [
    path('bootstrap/', BootstrapView.as_view()),
    path('register/', RegistrationView.as_view()),
    path('verify/', VerifyView.as_view()),
    path('resend/', ResendView.as_view()),
    path('login/', LoginView.as_view()),
    path('logout/', LogoutView.as_view()),
    path('me/', MeView.as_view()),
]
