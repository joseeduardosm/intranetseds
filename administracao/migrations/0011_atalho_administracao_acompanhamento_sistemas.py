from django.db import migrations, models


def seed_atalho_acompanhamento_sistemas(apps, schema_editor):
    AtalhoAdministracao = apps.get_model("administracao", "AtalhoAdministracao")
    AtalhoAdministracao.objects.get_or_create(
        funcionalidade="acompanhamento_sistemas",
        defaults={"ativo": True},
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("administracao", "0010_alter_atalhoadministracao_funcionalidade"),
    ]

    operations = [
        migrations.AlterField(
            model_name="atalhoadministracao",
            name="funcionalidade",
            field=models.CharField(
                choices=[
                    ("administracao", "Administracao"),
                    ("configuracoes", "Configuracoes"),
                    ("noticias", "Noticias"),
                    ("ramais", "Ramais"),
                    ("monitoramento", "Monitoramento"),
                    ("contratos", "Contratos"),
                    ("empresas", "Empresas"),
                    ("prepostos", "Prepostos"),
                    ("diario_bordo", "Diario de Bordo"),
                    ("folha_ponto", "Folha de Ponto"),
                    ("licitacoes", "Licitacoes"),
                    ("reserva_salas", "Reserva de Salas"),
                    ("sala_situacao", "Sala de Situacao"),
                    ("sala_situacao_old", "Sala de Situacao (Legado)"),
                    ("lousa_digital", "Lousa Digital"),
                    ("acompanhamento_sistemas", "Acompanhamento de Sistemas"),
                    ("rfs", "RFs"),
                    ("rh", "RH"),
                    ("usuarios", "Usuarios"),
                    ("auditoria", "Auditoria"),
                ],
                max_length=40,
                unique=True,
            ),
        ),
        migrations.RunPython(seed_atalho_acompanhamento_sistemas, noop_reverse),
    ]
