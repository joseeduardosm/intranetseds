from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reserva_salas", "0007_alter_reserva_options_alter_sala_cor"),
    ]

    operations = [
        migrations.AddField(
            model_name="sala",
            name="videowall",
            field=models.BooleanField(default=False, verbose_name="Videowall"),
        ),
        migrations.AddField(
            model_name="reserva",
            name="videowall",
            field=models.BooleanField(default=False, verbose_name="Videowall"),
        ),
    ]
