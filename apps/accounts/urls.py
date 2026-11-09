from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .password_reset import PasswordResetConfirmView, PasswordResetRequestView
from .views import (
    AreaViewSet,
    CompanyRegisterView,
    CompanyView,
    MeView,
    PrivacyConsentView,
    PrivacyView,
    RegisterView,
    SSTTokenObtainPairView,
    SSTTokenRefreshView,
    SSTTokenVerifyView,
    UserViewSet,
)

router = DefaultRouter()
router.register("areas", AreaViewSet, basename="area")
router.register("users", UserViewSet, basename="user")

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("register-company/", CompanyRegisterView.as_view(), name="register-company"),
    path("login/", SSTTokenObtainPairView.as_view(), name="login"),
    path("refresh/", SSTTokenRefreshView.as_view(), name="token-refresh"),
    path("verify/", SSTTokenVerifyView.as_view(), name="token-verify"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("me/", MeView.as_view(), name="me"),
    path("company/", CompanyView.as_view(), name="company"),
    path("privacy/", PrivacyView.as_view(), name="privacy"),
    path("privacy/consent/", PrivacyConsentView.as_view(), name="privacy-consent"),
    path("", include(router.urls)),
]
