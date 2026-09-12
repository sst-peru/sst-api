from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, viewsets
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Area
from .serializers import (
    AreaSerializer,
    RegisterSerializer,
    SSTTokenObtainPairSerializer,
    UserSerializer,
)

User = get_user_model()


class SSTTokenObtainPairView(TokenObtainPairView):
    serializer_class = SSTTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = (permissions.AllowAny,)
    queryset = User.objects.all()


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class AreaViewSet(viewsets.ModelViewSet):
    serializer_class = AreaSerializer

    def get_queryset(self):
        return Area.objects.filter(company=self.request.user.company_id)

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)
