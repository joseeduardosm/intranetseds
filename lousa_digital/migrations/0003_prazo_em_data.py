from datetime import timedelta

from django.db import migrations, models


def converter_minutos_para_data(apps, schema_editor):
    Encaminhamento = apps.get_model("lousa_digital", "Encaminhamento")

    for item in Encaminhamento.objects.all():
        minutos = getattr(item, "prazo_em_minutos", 0) or 0
        prazo_datetime = item.data_inicio + timedelta(minutes=minutos)
        item.prazo_data_tmp = prazo_datetime.date()
        item.save(update_fields=["prazo_data_tmp"])


class Migration(migrations.Migration):

    dependencies = [
        ("lousa_digital", "0002_origem_destino_texto_livre"),
    ]

    operations = [
        migrations.AddField(
            model_name="encaminhamento",
            name="prazo_data_tmp",
            field=models.DateField(default="2000-01-01", verbose_name="Prazo"),
            preserve_default=False,
        ),
        migrations.RunPython(converter_minutos_para_data, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="encaminhamento",
            name="prazo_em_minutos",
        ),
        migrations.RenameField(
            model_name="encaminhamento",
            old_name="prazo_data_tmp",
            new_name="prazo_data",
        ),
    ]
