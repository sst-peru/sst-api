from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Area, Company, Role

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
    """Registro público, usado igual por la web y por la app móvil.

    El rol NO se acepta del cliente: quien se registra por su cuenta entra siempre como
    OPERARIO. Si se aceptara, cualquiera podría registrarse como supervisor y cerrar sus
    propios hallazgos, que es justo el control que la ley exige separar. Para crear
    supervisores o miembros del comité existe /auth/users/, que requiere ser manager.
    """

    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    company_ruc = serializers.CharField(write_only=True, max_length=11)

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "password", "password_confirm",
            "first_name", "last_name", "dni", "phone", "company_ruc", "area",
        )

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Las contraseñas no coinciden."})

        ruc = attrs.pop("company_ruc")
        try:
            attrs["company"] = Company.objects.get(ruc=ruc)
        except Company.DoesNotExist:
            raise serializers.ValidationError(
                {"company_ruc": "No hay una empresa registrada con ese RUC. Pídeselo a tu supervisor."}
            ) from None

        area = attrs.get("area")
        if area and area.company_id != attrs["company"].id:
            raise serializers.ValidationError({"area": "El área no pertenece a esa empresa."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data, role=Role.OPERARIO)
        user.set_password(password)
        user.save()
        return user


class UserWriteSerializer(serializers.ModelSerializer):
    """Alta de usuarios hecha por un manager: aquí sí se puede fijar el rol."""

    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "password", "first_name", "last_name",
            "dni", "phone", "area", "role",
        )

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
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
