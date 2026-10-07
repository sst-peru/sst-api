from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import POLITICA_PRIVACIDAD_VERSION, Area, Company, PrivacyConsent, Role

User = get_user_model()

# Prefijos reales de RUC en el padrón de SUNAT: 10 y 15/16/17 para persona natural con
# negocio, 20 para persona jurídica. Cualquier otro par inicial es un error de tipeo.
RUC_PREFIJOS = ("10", "15", "16", "17", "20")


def validar_ruc(valor):
    """Valida la forma de un RUC peruano y devuelve un mensaje distinto por tipo de error.

    A propósito no se comprueba el dígito verificador módulo 11: dejaría fuera los RUC de
    prueba del seed de demostración y de los tests, y la forma ya atrapa los errores de
    tipeo que de verdad ocurren al registrarse.
    """
    if not valor.isdigit():
        raise serializers.ValidationError("El RUC solo admite dígitos, sin guiones ni espacios.")
    if len(valor) != 11:
        raise serializers.ValidationError(
            "El RUC debe tener exactamente 11 dígitos; escribiste %d." % len(valor)
        )
    if not valor.startswith(RUC_PREFIJOS):
        raise serializers.ValidationError(
            "Ese RUC no es válido: los RUC peruanos empiezan en 10, 15, 16, 17 o 20."
        )
    return valor


def validar_dni(valor):
    """El DNI es opcional, pero si viene tiene que tener sus 8 dígitos."""
    if valor and (not valor.isdigit() or len(valor) != 8):
        raise serializers.ValidationError("El DNI debe tener exactamente 8 dígitos.")
    return valor


class CompanySerializer(serializers.ModelSerializer):
    """Datos de la empresa. Es también el serializer de /auth/company/, donde el
    administrador corrige la razón social, la dirección y el número de trabajadores.

    El RUC es de solo lectura: es la llave con la que los trabajadores se registran y la
    que identifica a la empresa ante SUNAFIL. Cambiarlo dejaría a la plantilla sin poder
    darse de alta.
    """

    requires_committee = serializers.BooleanField(read_only=True)
    worker_accounts = serializers.IntegerField(read_only=True)
    worker_slots_available = serializers.IntegerField(read_only=True)

    class Meta:
        model = Company
        fields = (
            "id", "name", "ruc", "address", "worker_count",
            "requires_committee", "worker_accounts", "worker_slots_available",
        )
        read_only_fields = ("ruc",)
        extra_kwargs = {
            "worker_count": {
                "min_value": 1,
                "error_messages": {
                    "min_value": "La empresa debe tener al menos 1 trabajador.",
                    "invalid": "El número de trabajadores debe ser un número entero.",
                },
            },
        }

    def validate_worker_count(self, value):
        """No se puede declarar menos trabajadores de los que ya tienen cuenta.

        Si se permitiera, las cuentas que sobran quedarían activas sin plaza y el tope
        dejaría de significar algo.
        """
        registradas = self.instance.worker_accounts if self.instance else 0
        if value < registradas:
            raise serializers.ValidationError(
                "Ya hay %d cuentas de trabajador registradas: no puedes declarar menos de %d. "
                "Desactiva primero las cuentas que sobren." % (registradas, registradas)
            )
        return value


class AreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Area
        fields = ("id", "name", "description", "is_active")


class UserSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True, default=None)
    # Los clientes lo leen al iniciar sesion: si no hay consentimiento vigente, la web y
    # el movil muestran la politica antes de dejar reportar.
    has_accepted_privacy_policy = serializers.BooleanField(read_only=True)
    company_is_demo = serializers.BooleanField(source="company.is_demo", read_only=True)

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name",
            "role", "dni", "phone", "company", "company_name", "area", "area_name",
            "location_sharing", "has_accepted_privacy_policy", "company_is_demo",
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
    company_ruc = serializers.CharField(
        write_only=True,
        max_length=11,
        error_messages={
            "required": "Necesitamos el RUC de tu empresa para saber a cuál te sumas.",
            "blank": "Necesitamos el RUC de tu empresa para saber a cuál te sumas.",
            "max_length": "El RUC debe tener exactamente 11 dígitos.",
        },
    )

    def validate_company_ruc(self, valor):
        return validar_ruc(valor)

    def validate_dni(self, valor):
        return validar_dni(valor)

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

        empresa = attrs["company"]
        if not empresa.accepts_new_worker:
            raise serializers.ValidationError(
                {
                    "company_ruc": (
                        "%s declaró %d trabajador%s y ya tiene esas cuentas registradas. "
                        "Pídele a tu administrador de SST que actualice el número de "
                        "trabajadores de la empresa para que puedas registrarte."
                        % (
                            empresa.name,
                            empresa.worker_count,
                            "" if empresa.worker_count == 1 else "es",
                        )
                    )
                }
            )

        area = attrs.get("area")
        if area and area.company_id != empresa.id:
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

    def validate(self, attrs):
        """El tope de cuentas vale también para el alta manual.

        Si solo se comprobara en el registro público, un manager podría pasarse el cupo
        creando cuentas desde el panel y el número declarado no significaría nada.
        """
        if self.instance is None and attrs.get("role") != Role.ADMIN:
            empresa = self.context["request"].user.company
            if empresa and not empresa.accepts_new_worker:
                raise serializers.ValidationError(
                    {
                        "role": (
                            "Tu empresa declaró %d trabajador%s y ya tiene esas cuentas "
                            "registradas. Sube el número de trabajadores en los datos de la "
                            "empresa antes de crear otra cuenta."
                            % (
                                empresa.worker_count,
                                "" if empresa.worker_count == 1 else "es",
                            )
                        )
                    }
                )
        return attrs

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
    name = serializers.CharField(
        max_length=200,
        min_length=3,
        error_messages={
            "required": "Escribe la razón social de la empresa.",
            "blank": "Escribe la razón social de la empresa.",
            "min_length": "La razón social es muy corta: necesita al menos 3 caracteres.",
            "max_length": "La razón social no puede pasar de 200 caracteres.",
        },
    )
    ruc = serializers.CharField(
        max_length=11,
        error_messages={
            "required": "Escribe el RUC de la empresa.",
            "blank": "Escribe el RUC de la empresa.",
            "max_length": "El RUC debe tener exactamente 11 dígitos.",
        },
    )
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    worker_count = serializers.IntegerField(
        min_value=1,
        max_value=1_000_000,
        error_messages={
            "required": "Indica cuántos trabajadores tiene la empresa.",
            "invalid": "El número de trabajadores debe ser un número entero.",
            "min_value": (
                "La empresa debe tener al menos 1 trabajador: sin trabajadores no hay "
                "sistema de gestión de SST que administrar."
            ),
            "max_value": "Revisa el número de trabajadores: 1 000 000 es el máximo admitido.",
        },
    )

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
        validar_ruc(value)
        if Company.objects.filter(ruc=value).exists():
            raise serializers.ValidationError(
                "Ya hay una empresa registrada con ese RUC. Si trabajas ahí, "
                "regístrate como trabajador."
            )
        return value

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Ese usuario ya está tomado, elige otro.")
        return value

    def validate_dni(self, value):
        return validar_dni(value)

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


class PrivacyConsentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrivacyConsent
        fields = ("id", "policy_version", "granted_at", "revoked_at", "source")


class PrivacyStateSerializer(serializers.Serializer):
    """Estado de privacidad del usuario: consentimiento vigente y uso de la ubicación."""

    policy_version = serializers.CharField(read_only=True)
    accepted = serializers.BooleanField(read_only=True)
    granted_at = serializers.DateTimeField(read_only=True, allow_null=True)
    location_sharing = serializers.BooleanField()
    history = PrivacyConsentSerializer(many=True, read_only=True)

    @staticmethod
    def estado(user):
        consentimiento = user.privacy_consent
        return {
            "policy_version": POLITICA_PRIVACIDAD_VERSION,
            "accepted": consentimiento is not None,
            "granted_at": consentimiento.granted_at if consentimiento else None,
            "location_sharing": user.location_sharing,
            "history": PrivacyConsentSerializer(user.consents.all(), many=True).data,
        }


class PrivacyConsentWriteSerializer(serializers.Serializer):
    """Otorgamiento del consentimiento. El cliente declara desde dónde se dio."""

    source = serializers.ChoiceField(
        choices=PrivacyConsent.Source.choices, default=PrivacyConsent.Source.WEB
    )
    accept_policy_version = serializers.CharField(
        help_text="Versión de la política que el usuario está aceptando."
    )

    def validate_accept_policy_version(self, value):
        """Se rechaza aceptar una versión que no es la vigente.

        Si el cliente quedó con una copia vieja de la política, lo que el usuario leyó no
        es lo que estaría aceptando, y el consentimiento dejaría de ser informado.
        """
        if value != POLITICA_PRIVACIDAD_VERSION:
            raise serializers.ValidationError(
                "La política vigente es la versión %s. Vuelve a cargar la página para "
                "leerla antes de aceptarla." % POLITICA_PRIVACIDAD_VERSION
            )
        return value
