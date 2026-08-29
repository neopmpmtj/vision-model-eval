import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class EvaluationRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image = models.ImageField(upload_to="uploads/%Y/%m/%d/")
    image_name = models.CharField(max_length=255)
    image_content_type = models.CharField(max_length=100, default="image/jpeg")
    prompt = models.TextField()
    model_order = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Run {self.id} ({self.image_name})"

    @property
    def total_models(self) -> int:
        return len(self.model_order)

    @property
    def rated_count(self) -> int:
        return self.ratings.count()

    @property
    def is_complete(self) -> bool:
        return self.rated_count >= self.total_models

    @property
    def current_index(self) -> int:
        return self.rated_count


class EvaluationRating(models.Model):
    run = models.ForeignKey(
        EvaluationRun,
        on_delete=models.CASCADE,
        related_name="ratings",
    )
    sample_index = models.PositiveIntegerField()
    sample_label = models.CharField(max_length=32)
    model = models.CharField(max_length=100)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    notes = models.TextField(blank=True)
    latency_seconds = models.FloatField(null=True, blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sample_index"]
        unique_together = [("run", "sample_index")]

    def __str__(self) -> str:
        return f"{self.sample_label} — {self.model} ({self.rating}/5)"
