from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="DailyPageVisit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("visited_on", models.DateField(verbose_name="Data da visita")),
                ("title", models.CharField(blank=True, max_length=255, verbose_name="Titulo")),
                ("path", models.CharField(max_length=512)),
                ("visit_count", models.PositiveIntegerField(default=0, verbose_name="Quantidade de visitas")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Atualizado em")),
            ],
            options={
                "verbose_name": "Visita diaria por pagina",
                "verbose_name_plural": "Visitas diarias por pagina",
                "ordering": ("-visited_on", "path"),
            },
        ),
        migrations.AddConstraint(
            model_name="dailypagevisit",
            constraint=models.UniqueConstraint(fields=("visited_on", "path"), name="unique_daily_page_visit_path"),
        ),
        migrations.AddIndex(
            model_name="dailypagevisit",
            index=models.Index(fields=["visited_on"], name="rastreamen_visited_0eb8d0_idx"),
        ),
        migrations.AddIndex(
            model_name="dailypagevisit",
            index=models.Index(fields=["path"], name="rastreamen_path_4b4d4a_idx"),
        ),
        migrations.AddIndex(
            model_name="dailypagevisit",
            index=models.Index(fields=["visited_on", "path"], name="rastreamen_visited_46303d_idx"),
        ),
    ]
