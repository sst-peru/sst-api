"""Envío de correo por el proveedor configurado, dejando constancia del resultado (TS19).

El proveedor se elige por variables de entorno (EMAIL_BACKEND, EMAIL_HOST, ...): en desarrollo
los correos salen por consola; en producción, por SMTP o el servicio que se configure, sin
tocar el código.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import EmailLog, EmailStatus

logger = logging.getLogger("sst.email")


def enviar_correo(*, kind: str, to: str, subject: str, body: str) -> bool:
    """Envía un correo de texto y registra si salió. Nunca levanta excepción: devuelve False."""
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
    except Exception as error:  # noqa: BLE001 - cualquier fallo del proveedor se registra
        logger.warning("No se pudo enviar el correo %s", kind, extra={"status": 502})
        EmailLog.objects.create(
            kind=kind, to=to, subject=subject, status=EmailStatus.FALLIDO, error=str(error)
        )
        return False
    EmailLog.objects.create(kind=kind, to=to, subject=subject, status=EmailStatus.ENVIADO)
    return True
