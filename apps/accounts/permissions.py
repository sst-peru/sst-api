"""Permisos y validaciones compartidos por los módulos del sistema de gestión."""
from rest_framework import permissions, serializers


class ManagerEscribe(permissions.BasePermission):
    """Toda la empresa lee; solo supervisor, comité o administrador registra y modifica.

    Es la regla de los registros obligatorios: el trabajador debe poder consultarlos, pero
    quien los mantiene es el responsable del sistema de gestión.
    """

    message = "Solo supervisor, comité de SST o administrador puede hacer esto."

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.can_manage)


def validar_de_la_empresa(instancia, empresa_id, campo, etiqueta):
    """Impide referenciar un objeto de otra empresa aunque se conozca su id."""
    if instancia is None:
        return
    propia = getattr(instancia, "company_id", None)
    if propia is None and hasattr(instancia, "area"):
        propia = getattr(instancia.area, "company_id", None)
    if propia != empresa_id:
        raise serializers.ValidationError({campo: f"{etiqueta} no pertenece a tu empresa."})
