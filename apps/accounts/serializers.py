from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Area, Company

User = get_user_model()


class CompanySerializer(serializers.ModelSerializer):
    requires_committee = serializers.BooleanField(read_only=True)

    class Meta:
        model = Company
        fields = ("id", "name", "ruc", "address", "worker_count", "requires_committee")


class AreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Area
        fields = ("id", "name", "description", "is_active")


class UserSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True, default=None)

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name",
            "role", "dni", "phone", "company", "company_name", "area", "area_name",
        )
        read_only_fields = ("role", "company")


class RegisterSerializer(serializers.ModelSerializer):
    """Registro usado tanto por la web como por la app móvil."""

    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "password", "password_confirm",
            "first_name", "last_name", "dni", "phone", "company", "area", "role",
        )

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Las contraseñas no coinciden."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class SSTTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Agrega rol y empresa al token para que los clientes no hagan una llamada extra."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["company_id"] = user.company_id
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data
