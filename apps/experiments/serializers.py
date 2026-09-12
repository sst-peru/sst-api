from rest_framework import serializers

from .models import Assignment, Experiment


class ExperimentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Experiment
        fields = (
            "id", "key", "name", "description", "variants",
            "is_active", "started_at", "ended_at",
        )


class AssignmentSerializer(serializers.ModelSerializer):
    experiment_key = serializers.CharField(source="experiment.key", read_only=True)

    class Meta:
        model = Assignment
        fields = ("id", "experiment", "experiment_key", "variant", "assigned_at")
