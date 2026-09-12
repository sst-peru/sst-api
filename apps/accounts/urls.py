from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .views import AreaViewSet, MeView, RegisterView, SSTTokenObtainPairView, UserViewSet

router = DefaultRouter()
router.register("areas", AreaViewSet, basename="area")
router.register("users", UserViewSet, basename="user")

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", SSTTokenObtainPairView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("verify/", TokenVerifyView.as_view(), name="token-verify"),
    path("me/", MeView.as_view(), name="me"),
    path("", include(router.urls)),
]
