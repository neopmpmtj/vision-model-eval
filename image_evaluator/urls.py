from django.urls import path

from . import views

app_name = "image_evaluator"

urlpatterns = [
    path("", views.PrepareView.as_view(), name="prepare"),
    path("run/<uuid:run_id>/", views.EvaluateView.as_view(), name="evaluate"),
    path("run/<uuid:run_id>/benchmark/", views.BenchmarkView.as_view(), name="benchmark"),
    path("run/<uuid:run_id>/results/", views.ResultsView.as_view(), name="results"),
    path("run/<uuid:run_id>/download/", views.DownloadCsvView.as_view(), name="download"),
    path("run/<uuid:run_id>/reset/", views.ResetView.as_view(), name="reset"),
    path("reset/", views.ResetView.as_view(), name="reset_prepare"),
]
