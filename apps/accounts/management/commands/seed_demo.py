"""Carga datos de demostración realistas para desarrollar y para la sustentación.

Uso:  python manage.py seed_demo
      python manage.py seed_demo --reset   (borra los datos de demo y los vuelve a crear)

Genera unos 60 días de historia: reportes en las dos variantes del experimento, hallazgos
cerrados con distintos tiempos de resolución (para que el MTTR tenga algo que promediar),
inspecciones cumplidas y vencidas, entregas de EPP y dos actas del comité con acuerdos.
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Area, Company, Role
from apps.committee.models import (
    Agreement,
    AgreementStatus,
    Committee,
    CommitteeMember,
    MemberRole,
    Meeting,
    Represents,
)
from apps.epp.models import EppDelivery, EppItem
from apps.experiments.models import Assignment, Experiment
from apps.inspections.models import Frequency, Inspection, InspectionSchedule, InspectionStatus
from apps.iperc.models import IpercEntry, IpercMatrix, MatrixStatus
from apps.reports.models import Category, Report, ReportAction, ReportKind, ReportStatus, Severity

User = get_user_model()
RUC_DEMO = "20123456789"


class Command(BaseCommand):
    help = "Carga una empresa de demo con historia de reportes, IPERC, EPP, inspecciones y actas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Borra la empresa de demo antes de crearla de nuevo.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(29783)  # Reproducible: la demo sale igual cada vez que la corres.

        if options["reset"]:
            Company.objects.filter(ruc=RUC_DEMO).delete()
            self.stdout.write("Datos de demo anteriores eliminados.")

        company, _ = Company.objects.get_or_create(
            ruc=RUC_DEMO,
            defaults={
                "name": "Constructora Los Andes S.A.C.",
                "address": "Av. Javier Prado Este 1234, San Isidro, Lima",
                "worker_count": 45,
            },
        )

        areas = {}
        for name, desc in [
            ("Obra Civil", "Frente de trabajo principal, incluye trabajos en altura"),
            ("Almacén", "Almacén de materiales y EPP"),
            ("Taller Eléctrico", "Mantenimiento de tableros y equipos"),
            ("Oficinas", "Administración y supervisión"),
        ]:
            areas[name], _ = Area.objects.get_or_create(
                company=company, name=name, defaults={"description": desc}
            )

        categorias = {}
        for name, kind in [
            ("No usa EPP obligatorio", ReportKind.ACTO),
            ("Trabajo en altura sin arnés", ReportKind.ACTO),
            ("Manipulación incorrecta de carga", ReportKind.ACTO),
            ("Operar equipo sin autorización", ReportKind.ACTO),
            ("Cable eléctrico expuesto", ReportKind.CONDICION),
            ("Piso mojado sin señalizar", ReportKind.CONDICION),
            ("Andamio o escalera en mal estado", ReportKind.CONDICION),
            ("Falta de orden y limpieza", ReportKind.CONDICION),
            ("Extintor vencido o bloqueado", ReportKind.CONDICION),
        ]:
            categorias[name], _ = Category.objects.get_or_create(
                company=company, name=name, kind=kind
            )

        usuarios = {}
        for username, role, first, last, dni, area in [
            ("supervisor", Role.SUPERVISOR, "Ana", "Quispe Mendoza", "45871203", "Oficinas"),
            ("comite1", Role.COMITE, "Luis", "Ramos Delgado", "41203985", "Obra Civil"),
            ("comite2", Role.COMITE, "Carmen", "Yupanqui Rojas", "43918276", "Almacén"),
            ("operario1", Role.OPERARIO, "José", "Huamán Ccala", "47201938", "Obra Civil"),
            ("operario2", Role.OPERARIO, "Marta", "Flores Inga", "46120384", "Obra Civil"),
            ("operario3", Role.OPERARIO, "Pedro", "Cáceres Loayza", "44983017", "Taller Eléctrico"),
            ("operario4", Role.OPERARIO, "Rosa", "Vargas Pineda", "48209174", "Almacén"),
            ("operario5", Role.OPERARIO, "Julio", "Tapia Meza", "42017365", "Obra Civil"),
            ("operario6", Role.OPERARIO, "Elena", "Chávez Soto", "45019283", "Taller Eléctrico"),
        ]:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "role": role,
                    "first_name": first,
                    "last_name": last,
                    "dni": dni,
                    "company": company,
                    "area": areas[area],
                    "email": f"{username}@losandes.pe",
                },
            )
            if created:
                user.set_password("demo12345")
                user.save()
            usuarios[username] = user

        supervisor = usuarios["supervisor"]
        operarios = [usuarios[f"operario{i}"] for i in range(1, 7)]

        # ----- Experimento A/B: asignación determinística por usuario -----
        experimento, _ = Experiment.objects.get_or_create(
            key=Experiment.KEY_REPORT_FORM,
            defaults={
                "name": "Formulario rápido vs formulario largo",
                "description": (
                    "Hipótesis: un formulario tipo asistente de 3-4 taps con foto duplica la "
                    "frecuencia de reportes frente al formulario tradicional de 10+ campos."
                ),
                "variants": ["rapido", "largo"],
                "is_active": True,
                "started_at": timezone.now() - timedelta(days=60),
            },
        )
        variantes = {}
        for operario in operarios:
            variante = experimento.variant_for(operario.id)
            Assignment.objects.get_or_create(
                experiment=experimento, user=operario, defaults={"variant": variante}
            )
            variantes[operario.id] = variante

        # ----- Reportes: 60 días de historia -----
        if not Report.objects.filter(company=company).exists():
            ahora = timezone.now()
            lista_categorias = list(categorias.values())
            for dia in range(60, 0, -1):
                for operario in operarios:
                    # El grupo del formulario rápido reporta más seguido: es la hipótesis
                    # del experimento reflejada en los datos de demo.
                    probabilidad = 0.30 if variantes[operario.id] == "rapido" else 0.15
                    if random.random() > probabilidad:
                        continue

                    categoria = random.choice(lista_categorias)
                    severidad = random.choices(
                        [Severity.BAJA, Severity.MEDIA, Severity.ALTA, Severity.CRITICA],
                        weights=[35, 40, 20, 5],
                    )[0]
                    creado = ahora - timedelta(days=dia, hours=random.randint(0, 9))

                    reporte = Report.objects.create(
                        company=company,
                        reported_by=operario,
                        kind=categoria.kind,
                        category=categoria,
                        area=operario.area,
                        description=f"{categoria.name} detectado en {operario.area.name}.",
                        severity=severidad,
                        latitude=-12.0464 + random.uniform(-0.01, 0.01),
                        longitude=-77.0428 + random.uniform(-0.01, 0.01),
                        occurred_at=creado,
                        form_variant=variantes[operario.id],
                        synced_offline=random.random() < 0.25,
                    )
                    # auto_now_add ignora el valor que pasemos, así que lo corregimos aquí.
                    Report.objects.filter(pk=reporte.pk).update(created_at=creado)
                    reporte.refresh_from_db()

                    # Los más graves se cierran más rápido: así el MTTR por severidad tiene
                    # sentido al mirarlo en el tablero.
                    horas_cierre = {
                        Severity.CRITICA: random.randint(2, 12),
                        Severity.ALTA: random.randint(8, 48),
                        Severity.MEDIA: random.randint(24, 120),
                        Severity.BAJA: random.randint(48, 300),
                    }[severidad]
                    cerrado = creado + timedelta(hours=horas_cierre)

                    if cerrado < ahora and random.random() < 0.75:
                        reporte.status = ReportStatus.CERRADO
                        reporte.assigned_to = supervisor
                        reporte.assigned_at = creado + timedelta(hours=horas_cierre / 3)
                        reporte.closed_at = cerrado
                        reporte.closure_note = "Se aplicó el control correctivo y se verificó en campo."
                        reporte.save()
                        ReportAction.objects.create(
                            report=reporte, author=supervisor,
                            note="Responsable asignado.", new_status=ReportStatus.EN_PROCESO,
                        )
                        ReportAction.objects.create(
                            report=reporte, author=supervisor,
                            note=reporte.closure_note, new_status=ReportStatus.CERRADO,
                        )
                    elif random.random() < 0.5:
                        reporte.status = ReportStatus.EN_PROCESO
                        reporte.assigned_to = supervisor
                        reporte.assigned_at = creado + timedelta(hours=6)
                        reporte.save()
                        ReportAction.objects.create(
                            report=reporte, author=supervisor,
                            note="En seguimiento.", new_status=ReportStatus.EN_PROCESO,
                        )

        # ----- Matriz IPERC alimentada por reportes reales -----
        matriz, creada = IpercMatrix.objects.get_or_create(
            company=company,
            version=1,
            defaults={
                "status": MatrixStatus.VIGENTE,
                "valid_from": timezone.localdate() - timedelta(days=40),
                "approved_by": supervisor,
            },
        )
        if creada:
            repetidos = (
                Report.objects.filter(company=company, severity__in=[Severity.ALTA, Severity.CRITICA])
                .select_related("category", "area")[:6]
            )
            base = [
                ("Albañil", "Trabajo en altura sobre andamio", "Caída a distinto nivel", 3, 3,
                 "Andamio certificado y arnés con doble línea de vida"),
                ("Electricista", "Contacto con energía eléctrica", "Electrocución", 2, 3,
                 "Bloqueo y etiquetado, guantes dieléctricos"),
                ("Almacenero", "Manipulación manual de carga", "Lesión lumbar", 3, 2,
                 "Capacitación en levantamiento y uso de transpaleta"),
                ("Operario de obra", "Piso resbaladizo", "Caída al mismo nivel", 2, 2,
                 "Señalización y limpieza inmediata de derrames"),
            ]
            for i, (puesto, peligro, riesgo, prob, cons, controles) in enumerate(base):
                origen = repetidos[i] if i < len(repetidos) else None
                IpercEntry.objects.create(
                    matrix=matriz,
                    area=origen.area if origen and origen.area else areas["Obra Civil"],
                    job_position=puesto,
                    hazard=peligro,
                    risk=riesgo,
                    probability=prob,
                    consequence=cons,
                    existing_controls=controles,
                    proposed_controls="Reforzar la inspección previa al inicio de la tarea.",
                    responsible=supervisor,
                    source_report=origen,
                )

        # ----- EPP -----
        epps = {}
        for nombre, vida, stock in [
            ("Casco de seguridad", 1095, 60),
            ("Guantes de cuero", 90, 200),
            ("Arnés de cuerpo completo", 730, 25),
            ("Lentes de seguridad", 180, 120),
            ("Botas con punta de acero", 365, 50),
        ]:
            epps[nombre], _ = EppItem.objects.get_or_create(
                company=company, name=nombre,
                defaults={"lifespan_days": vida, "stock": stock},
            )
        if not EppDelivery.objects.filter(item__company=company).exists():
            for operario in operarios:
                for nombre in ["Casco de seguridad", "Guantes de cuero", "Botas con punta de acero"]:
                    EppDelivery.objects.create(
                        item=epps[nombre],
                        worker=operario,
                        delivered_by=supervisor,
                        delivered_at=timezone.now() - timedelta(days=random.randint(30, 400)),
                        acknowledged=random.random() < 0.8,
                    )

        # ----- Inspecciones: algunas cumplidas, otras vencidas -----
        programas = []
        for titulo, area, frecuencia, checklist in [
            ("Inspección de andamios y líneas de vida", "Obra Civil", Frequency.SEMANAL,
             ["Andamios con arriostre completo", "Líneas de vida ancladas",
              "Accesos libres de obstáculos", "Rodapiés instalados"]),
            ("Inspección de tableros eléctricos", "Taller Eléctrico", Frequency.MENSUAL,
             ["Tableros rotulados y cerrados", "Sin cables expuestos",
              "Puesta a tierra verificada"]),
            ("Inspección de extintores y rutas de evacuación", "Almacén", Frequency.MENSUAL,
             ["Extintores con carga vigente", "Rutas libres y señalizadas",
              "Luces de emergencia operativas"]),
        ]:
            programa, _ = InspectionSchedule.objects.get_or_create(
                company=company, area=areas[area], title=titulo,
                defaults={"frequency": frecuencia, "checklist": checklist,
                          "responsible": supervisor},
            )
            programas.append(programa)

        if not Inspection.objects.filter(schedule__company=company).exists():
            hoy = timezone.localdate()
            for programa in programas:
                paso = Frequency.days(programa.frequency)
                fecha = hoy - timedelta(days=paso * 6)
                while fecha <= hoy + timedelta(days=paso):
                    inspeccion = Inspection.objects.create(schedule=programa, due_date=fecha)
                    if fecha < hoy:
                        if random.random() < 0.7:
                            inspeccion.status = InspectionStatus.REALIZADA
                            inspeccion.performed_at = timezone.make_aware(
                                timezone.datetime.combine(fecha, timezone.datetime.min.time())
                            ) + timedelta(hours=10)
                            inspeccion.performed_by = supervisor
                            inspeccion.findings = "Sin observaciones mayores."
                            inspeccion.results = {item: True for item in programa.checklist}
                        else:
                            inspeccion.status = InspectionStatus.PENDIENTE
                        inspeccion.save()
                    fecha += timedelta(days=paso)

        # ----- Comité de SST con actas -----
        comite, creado_comite = Committee.objects.get_or_create(
            company=company,
            defaults={
                "period_start": timezone.localdate() - timedelta(days=120),
                "period_end": timezone.localdate() + timedelta(days=610),
                "is_supervisor_mode": not company.requires_committee,
            },
        )
        if creado_comite:
            for user, cargo, representa in [
                (supervisor, MemberRole.PRESIDENTE, Represents.EMPLEADOR),
                (usuarios["comite1"], MemberRole.SECRETARIO, Represents.TRABAJADORES),
                (usuarios["comite2"], MemberRole.TITULAR, Represents.TRABAJADORES),
                (usuarios["operario1"], MemberRole.TITULAR, Represents.EMPLEADOR),
            ]:
                CommitteeMember.objects.create(
                    committee=comite, user=user, role=cargo, represents=representa
                )

            miembros = list(comite.members.all())
            for numero, dias_atras, agenda in [
                (1, 60, "Instalación del comité, revisión de la matriz IPERC y plan anual de SST."),
                (2, 30, "Revisión de hallazgos del mes y avance de acuerdos pendientes."),
            ]:
                acta = Meeting.objects.create(
                    committee=comite,
                    number=numero,
                    date=timezone.localdate() - timedelta(days=dias_atras),
                    place="Sala de reuniones - Oficina de obra",
                    agenda=agenda,
                    minutes=(
                        "Se revisaron los reportes de actos y condiciones inseguras del periodo. "
                        "Se acordaron las acciones correctivas detalladas en los acuerdos."
                    ),
                )
                acta.attendees.set(miembros)

                criticos = Report.objects.filter(
                    company=company, severity=Severity.CRITICA
                ).first()
                Agreement.objects.create(
                    meeting=acta,
                    description="Reforzar la capacitación en trabajos en altura para todo el frente de obra.",
                    responsible=supervisor,
                    due_date=acta.date + timedelta(days=30),
                    status=AgreementStatus.CUMPLIDO if numero == 1 else AgreementStatus.EN_PROCESO,
                )
                Agreement.objects.create(
                    meeting=acta,
                    description="Reponer los extintores con carga vencida del almacén.",
                    responsible=usuarios["operario4"],
                    due_date=acta.date + timedelta(days=15),
                    status=AgreementStatus.CUMPLIDO if numero == 1 else AgreementStatus.PENDIENTE,
                    related_report=criticos,
                )

        # ----- Resumen -----
        total = Report.objects.filter(company=company).count()
        cerrados = Report.objects.filter(company=company, status=ReportStatus.CERRADO).count()
        self.stdout.write(self.style.SUCCESS("\nDatos de demo listos:"))
        self.stdout.write(f"  Empresa:      {company.name} (RUC {company.ruc})")
        self.stdout.write(f"  Usuarios:     {User.objects.filter(company=company).count()} (clave: demo12345)")
        self.stdout.write(f"  Reportes:     {total} ({cerrados} cerrados)")
        self.stdout.write(f"  IPERC:        {IpercEntry.objects.filter(matrix__company=company).count()} entradas")
        self.stdout.write(f"  EPP:          {EppDelivery.objects.filter(item__company=company).count()} entregas")
        self.stdout.write(f"  Inspecciones: {Inspection.objects.filter(schedule__company=company).count()}")
        self.stdout.write(f"  Actas:        {Meeting.objects.filter(committee=comite).count()}")
        self.stdout.write("\n  Variantes del experimento A/B:")
        for operario in operarios:
            n = Report.objects.filter(reported_by=operario).count()
            self.stdout.write(f"    {operario.username:12} {variantes[operario.id]:8} {n} reportes")
        self.stdout.write("\n  Entra con: supervisor / demo12345\n")
