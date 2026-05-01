"""Modelos persistidos para estatisticas agregadas de navegacao."""

from django.db import models


class DailyPageVisit(models.Model):
    """Agregado diario de visualizacoes por caminho acessado."""

    visited_on = models.DateField("Data da visita")
    title = models.CharField("Titulo", max_length=255, blank=True)
    path = models.CharField("Caminho", max_length=512)
    visit_count = models.PositiveIntegerField("Quantidade de visitas", default=0)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Visita diaria por pagina"
        verbose_name_plural = "Visitas diarias por pagina"
        ordering = ("-visited_on", "path")
        constraints = [
            models.UniqueConstraint(
                fields=("visited_on", "path"),
                name="unique_daily_page_visit_path",
            )
        ]
        indexes = [
            models.Index(fields=("visited_on",)),
            models.Index(fields=("path",)),
            models.Index(fields=("visited_on", "path")),
        ]

    def __str__(self) -> str:
        return f"{self.visited_on} - {self.path} ({self.visit_count})"
