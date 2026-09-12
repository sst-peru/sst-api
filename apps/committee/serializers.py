from rest_framework import serializers

from .models import Agreement, Committee, CommitteeMember, Meeting


class CommitteeMemberSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = CommitteeMember
        fields = ("id", "committee", "user", "user_name", "role", "represents", "is_active")


class AgreementSerializer(serializers.ModelSerializer):
    responsible_name = serializers.CharField(
        source="responsible.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = Agreement
        fields = (
            "id", "meeting", "description", "responsible", "responsible_name",
            "due_date", "status", "related_report", "related_iperc_entry",
        )


class MeetingSerializer(serializers.ModelSerializer):
    agreements = AgreementSerializer(many=True, read_only=True)
    attendee_count = serializers.IntegerField(read_only=True)
    quorum_reached = serializers.BooleanField(read_only=True)

    class Meta:
        model = Meeting
        fields = (
            "id", "committee", "number", "date", "place", "is_extraordinary",
            "agenda", "minutes", "attendees", "attendee_count", "quorum_reached",
            "agreements", "created_at",
        )
        read_only_fields = ("created_at",)


class CommitteeSerializer(serializers.ModelSerializer):
    members = CommitteeMemberSerializer(many=True, read_only=True)
    member_count = serializers.IntegerField(read_only=True)
    quorum_required = serializers.IntegerField(read_only=True)
    is_paritario = serializers.BooleanField(read_only=True)

    class Meta:
        model = Committee
        fields = (
            "id", "period_start", "period_end", "is_supervisor_mode",
            "members", "member_count", "quorum_required", "is_paritario",
        )
