"""Crea datos de demostración para desarrollar y para la sustentación.

Uso: python manage.py seed_demo
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Area, Company, Role
from apps.experiments.models import Experiment
from apps.inspections.models import Frequency, InspectionSchedule
from apps.reports.models import Category, ReportKind

User = get_user_model()


class Command(BaseCommand):
    help = "Carga una empresa, áreas, categorías, usuarios y el experimento A/B de demo."

    def handle(self, *args, **options):
        company, _ = Company.objects.get_or_create(
            ruc="20123456789",
            defaults={"name": "Constructora Los Andes S.A.C.", "worker_count": 45},
        )
        areas = {}
        for name in ["Obra Civil", "Almacén", "Taller Eléctrico", "Oficinas"]:
            areas[name], _ = Area.objects.get_or_create(company=company, name=name)

        categorias = [
            ("No usa EPP", ReportKind.ACTO),
            ("Trabajo en altura sin arnés", ReportKind.ACTO),
            ("Manipulación incorrecta de carga", ReportKind.ACTO),
            ("Cable eléctrico expuesto", ReportKind.CONDICION),
            ("Piso mojado sin señalizar", ReportKind.CONDICION),
            ("Andamio o escalera en mal estado", ReportKind.CONDICION),
            ("Falta de orden y limpieza", ReportKind.CONDICION),
        ]
        for name, kind in categorias:
            Category.objects.get_or_create(company=company, name=name, kind=kind)

        usuarios = [
            ("supervisor", Role.SUPERVISOR, "Ana", "Quispe"),
            ("comite1", Role.COMITE, "Luis", "Ramos"),
            ("operario1", Role.OPERARIO, "José", "Huamán"),
            ("operario2", Role.OPERARIO, "Marta", "Flores"),
            ("operario3", Role.OPERARIO, "Pedro", "Cáceres"),
            ("operario4", Role.OPERARIO, "Rosa", "Vargas"),
        ]
        for username, role, first, last in usuarios:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "role": role,
                    "first_name": first,
                    "last_name": last,
                    "company": company,
                    "area": areas["Obra Civil"],
                    "email": f"{username}@demo.pe",
                },
            )
            if created:
                user.set_password("demo12345")
                user.save()

        InspectionSchedule.objects.get_or_create(
            company=company,
            area=areas["Obra Civil"],
            title="Inspección de andamios y líneas de vida",
            defaults={
                "frequency": Frequency.SEMANAL,
                "checklist": [
                    "Andamios con arriostre completo",
                    "Líneas de vida ancladas",
                    "Accesos libres de obstáculos",
                ],
            },
        )

        Experiment.objects.get_or_create(
            key=Experiment.KEY_REPORT_FORM,
            defaults={
                "name": "Formulario rápido vs formulario largo",
                "description": (
                    "Hipótesis: un formulario tipo asistente de 3-4 taps con foto duplica la "
                    "frecuencia de reportes frente al formulario tradicional de 10+ campos."
                ),
                "variants": ["rapido", "largo"],
                "is_active": True,
                "started_at": timezone.now(),
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Datos de demo listos. Usuarios: supervisor / operario1..4 — clave: demo12345"
            )
        )
