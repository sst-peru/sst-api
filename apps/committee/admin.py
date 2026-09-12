from django.contrib import admin

from .models import Agreement, Committee, CommitteeMember, Meeting


class MemberInline(admin.TabularInline):
    model = CommitteeMember
    extra = 0


class AgreementInline(admin.TabularInline):
    model = Agreement
    extra = 0


@admin.register(Committee)
class CommitteeAdmin(admin.ModelAdmin):
    list_display = ("company", "period_start", "period_end", "is_supervisor_mode", "is_paritario")
    inlines = (MemberInline,)


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ("number", "date", "committee", "is_extraordinary", "quorum_reached")
    list_filter = ("committee", "is_extraordinary")
    inlines = (AgreementInline,)


@admin.register(Agreement)
class AgreementAdmin(admin.ModelAdmin):
    list_display = ("description", "responsible", "due_date", "status")
    list_filter = ("status",)
