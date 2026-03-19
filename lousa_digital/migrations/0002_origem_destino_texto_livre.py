from django.db import migrations, models


def copiar_origem_destino_para_texto(apps, schema_editor):
    Caixa = apps.get_model("lousa_digital", "Caixa")
    Processo = apps.get_model("lousa_digital", "Processo")
    Encaminhamento = apps.get_model("lousa_digital", "Encaminhamento")

    caixas = {caixa.pk: caixa.nome for caixa in Caixa.objects.all()}

    for processo in Processo.objects.all():
        nome = caixas.get(getattr(processo, "caixa_origem_id", None), "")
        processo.caixa_origem_texto = nome
        processo.save(update_fields=["caixa_origem_texto"])

    for encaminhamento in Encaminhamento.objects.all():
        nome = caixas.get(getattr(encaminhamento, "destino_id", None), "")
        encaminhamento.destino_texto = nome
        encaminhamento.save(update_fields=["destino_texto"])


class Migration(migrations.Migration):

    dependencies = [
        ("lousa_digital", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="processo",
            name="caixa_origem_texto",
            field=models.CharField(default="", max_length=180),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="encaminhamento",
            name="destino_texto",
            field=models.CharField(default="", max_length=180),
            preserve_default=False,
        ),
        migrations.RunPython(copiar_origem_destino_para_texto, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="processo",
            name="caixa_origem",
        ),
        migrations.RemoveField(
            model_name="encaminhamento",
            name="destino",
        ),
        migrations.DeleteModel(
            name="Caixa",
        ),
        migrations.RenameField(
            model_name="processo",
            old_name="caixa_origem_texto",
            new_name="caixa_origem",
        ),
        migrations.RenameField(
            model_name="encaminhamento",
            old_name="destino_texto",
            new_name="destino",
        ),
    ]
