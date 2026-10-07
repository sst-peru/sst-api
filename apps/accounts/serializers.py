from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
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


class CompanyRegisterSerializer(serializers.Serializer):
    """Alta de una empresa nueva junto con la cuenta de su administrador.

    Es el otro camino de registro. En /auth/register/ el trabajador se suma a una empresa
    que ya existe y el RUC tiene que encontrarse; aquí la empresa se crea y el RUC tiene que
    estar libre. Son validaciones opuestas, y por eso van en endpoints separados en vez de
    uno solo con un campo "tipo" y la mitad de los campos obligatorios a medias.

    Quien registra la empresa queda como ADMIN. En ese momento no existe ningún otro
    usuario, y alguien tiene que poder crear las áreas y las cuentas de supervisor y de
    comité de SST que exige la Ley 29783.
    """

    # Datos de la empresa
    name = serializers.CharField(max_length=200)
    ruc = serializers.CharField(max_length=11)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    worker_count = serializers.IntegerField(min_value=1)

    # Cuenta del administrador
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    dni = serializers.CharField(max_length=8, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    def validate_ruc(self, value):
        if not value.isdigit() or len(value) != 11:
            raise serializers.ValidationError("El RUC debe tener 11 dígitos numéricos.")
        if Company.objects.filter(ruc=value).exists():
            raise serializers.ValidationError(
                "Ya hay una empresa registrada con ese RUC. Si trabajas ahí, "
                "regístrate como trabajador."
            )
        return value

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Ese usuario ya está tomado.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Las contraseñas no coinciden."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """La empresa y su administrador se crean juntos o no se crean.

        Sin la transacción, un error al guardar el usuario dejaría la empresa creada y su
        RUC tomado, y el dueño no podría volver a intentarlo.
        """
        company = Company.objects.create(
            name=validated_data["name"],
            ruc=validated_data["ruc"],
            address=validated_data["address"],
            worker_count=validated_data["worker_count"],
        )
        user = User(
            username=validated_data["username"],
            email=validated_data["email"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            dni=validated_data["dni"],
            phone=validated_data["phone"],
            company=company,
            role=Role.ADMIN,
        )
        user.set_password(validated_data["password"])
        user.save()
        return user

    def to_representation(self, instance):
        return {
            "user": UserSerializer(instance).data,
            "company": CompanySerializer(instance.company).data,
        }
