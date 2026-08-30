import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class RunStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "In progress"
    COMPLETED = "completed", "Completed"
    ABANDONED = "abandoned", "Abandoned"


class TurnStatus(models.TextChoices):
    SUCCESS = "success", "Success"
    ERROR = "error", "Error"


class EvaluationRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image = models.ImageField(upload_to="uploads/%Y/%m/%d/")
    image_name = models.CharField(max_length=255)
    image_content_type = models.CharField(max_length=100, default="image/jpeg")
    image_size_bytes = models.PositiveIntegerField(null=True, blank=True)
    image_width = models.PositiveIntegerField(null=True, blank=True)
    image_height = models.PositiveIntegerField(null=True, blank=True)
    prompt = models.TextField()
    description = models.TextField(blank=True, default="")
    model_order = models.JSONField(default=list)
    api_defaults = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=RunStatus.choices,
        default=RunStatus.IN_PROGRESS,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Run {self.id} ({self.image_name})"

    @property
    def is_benchmark(self) -> bool:
        return hasattr(self, "latency_benchmark")

    @property
    def total_models(self) -> int:
        return len(self.model_order)

    @property
    def turn_count(self) -> int:
        return self.turns.count()

    @property
    def generated_count(self) -> int:
        return self.turns.filter(status=TurnStatus.SUCCESS).count()

    @property
    def rated_count(self) -> int:
        return self.turns.filter(rating__isnull=False).count()

    @property
    def is_complete(self) -> bool:
        if self.total_models == 0:
            return False
        if self.is_benchmark:
            benchmark = getattr(self, "latency_benchmark", None)
            return (
                self.turn_count >= self.total_models
                and benchmark is not None
                and benchmark.status == RunStatus.COMPLETED
            )
        return self.rated_count >= self.total_models

    @property
    def current_index(self) -> int:
        if self.is_benchmark:
            return self.turn_count
        return self.rated_count


class LatencyBenchmark(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.OneToOneField(
        EvaluationRun,
        on_delete=models.CASCADE,
        related_name="latency_benchmark",
    )
    status = models.CharField(
        max_length=20,
        choices=RunStatus.choices,
        default=RunStatus.IN_PROGRESS,
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    turn_count_expected = models.PositiveIntegerField(default=0)
    successful_turn_count = models.PositiveIntegerField(default=0)
    failed_turn_count = models.PositiveIntegerField(default=0)
    total_wall_latency_seconds = models.FloatField(null=True, blank=True)
    avg_wall_latency_seconds = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"Benchmark {self.id} (run {self.run_id})"

    def refresh_aggregates(self) -> None:
        turns = self.run.turns.all()
        successful = turns.filter(status=TurnStatus.SUCCESS)
        failed = turns.filter(status=TurnStatus.ERROR)
        latencies = [
            value
            for value in successful.values_list("latency_wall_seconds", flat=True)
            if value is not None
        ]
        self.successful_turn_count = successful.count()
        self.failed_turn_count = failed.count()
        if latencies:
            self.total_wall_latency_seconds = round(sum(latencies), 3)
            self.avg_wall_latency_seconds = round(sum(latencies) / len(latencies), 3)
        else:
            self.total_wall_latency_seconds = None
            self.avg_wall_latency_seconds = None


class EvaluationTurn(models.Model):
    run = models.ForeignKey(
        EvaluationRun,
        on_delete=models.CASCADE,
        related_name="turns",
    )
    turn_index = models.PositiveIntegerField()
    sample_label = models.CharField(max_length=32)
    model = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=TurnStatus.choices,
        default=TurnStatus.SUCCESS,
    )
    response_text = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    error_type = models.CharField(max_length=255, blank=True)
    openai_response_id = models.CharField(max_length=255, blank=True)
    response_model = models.CharField(max_length=100, blank=True)
    openai_status = models.CharField(max_length=50, blank=True)
    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    notes = models.TextField(blank=True)
    rated_at = models.DateTimeField(null=True, blank=True)
    request_started_at = models.DateTimeField(null=True, blank=True)
    request_finished_at = models.DateTimeField(null=True, blank=True)
    latency_wall_seconds = models.FloatField(null=True, blank=True)
    latency_openai_seconds = models.FloatField(null=True, blank=True)
    time_to_first_token_seconds = models.FloatField(null=True, blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    total_tokens = models.PositiveIntegerField(null=True, blank=True)
    reasoning_tokens = models.PositiveIntegerField(null=True, blank=True)
    cached_tokens = models.PositiveIntegerField(null=True, blank=True)
    cache_write_tokens = models.PositiveIntegerField(null=True, blank=True)
    usage_raw = models.JSONField(default=dict, blank=True)
    api_request = models.JSONField(default=dict, blank=True)
    api_response = models.JSONField(default=dict, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["turn_index"]
        unique_together = [("run", "turn_index")]

    def __str__(self) -> str:
        if self.rating is not None:
            return f"{self.sample_label} — {self.model} ({self.rating}/5)"
        return f"{self.sample_label} — {self.model} ({self.status})"
