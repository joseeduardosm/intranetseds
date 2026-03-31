from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Sistema",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=180)),
                ("descricao", models.TextField()),
                ("url_homologacao", models.URLField(blank=True)),
                ("url_producao", models.URLField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sistemas_acompanhamento_atualizados", to=settings.AUTH_USER_MODEL)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sistemas_acompanhamento_criados", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["nome"], "verbose_name": "Sistema", "verbose_name_plural": "Sistemas"},
        ),
        migrations.CreateModel(
            name="EntregaSistema",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=180)),
                ("descricao", models.TextField(blank=True)),
                ("ordem", models.PositiveIntegerField(default=1)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="entregas_sistema_atualizadas", to=settings.AUTH_USER_MODEL)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="entregas_sistema_criadas", to=settings.AUTH_USER_MODEL)),
                ("sistema", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entregas", to="acompanhamento_sistemas.sistema")),
            ],
            options={"ordering": ["ordem", "id"], "verbose_name": "Entrega do sistema", "verbose_name_plural": "Entregas do sistema", "unique_together": {("sistema", "ordem")}},
        ),
        migrations.CreateModel(
            name="EtapaSistema",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_etapa", models.CharField(choices=[("REQUISITOS", "Requisitos"), ("HOMOLOGACAO_REQUISITOS", "Homologacao de Requisitos"), ("DESENVOLVIMENTO", "Desenvolvimento"), ("HOMOLOGACAO_DESENVOLVIMENTO", "Homologacao do Desenvolvimento"), ("PRODUCAO", "Producao")], max_length=40)),
                ("data_etapa", models.DateField()),
                ("status", models.CharField(choices=[("PENDENTE", "Pendente"), ("EM_ANDAMENTO", "Em andamento"), ("ENTREGUE", "Entregue")], default="PENDENTE", max_length=20)),
                ("ordem", models.PositiveIntegerField(default=1)),
                ("tempo_desde_etapa_anterior_em_dias", models.IntegerField(blank=True, null=True)),
                ("ticket_externo", models.CharField(blank=True, max_length=120)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="etapas_sistema_atualizadas", to=settings.AUTH_USER_MODEL)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="etapas_sistema_criadas", to=settings.AUTH_USER_MODEL)),
                ("entrega", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="etapas", to="acompanhamento_sistemas.entregasistema")),
            ],
            options={"ordering": ["ordem", "id"], "verbose_name": "Etapa do sistema", "verbose_name_plural": "Etapas do sistema", "unique_together": {("entrega", "tipo_etapa")}},
        ),
        migrations.CreateModel(
            name="HistoricoEtapaSistema",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_evento", models.CharField(choices=[("STATUS", "Status"), ("DATA", "Data"), ("NOTA", "Nota"), ("ANEXO", "Anexo"), ("CRIACAO", "Criacao")], max_length=20)),
                ("descricao", models.TextField(blank=True)),
                ("status_anterior", models.CharField(blank=True, max_length=20)),
                ("status_novo", models.CharField(blank=True, max_length=20)),
                ("data_anterior", models.DateField(blank=True, null=True)),
                ("data_nova", models.DateField(blank=True, null=True)),
                ("justificativa", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="historicos_etapa_sistema_criados", to=settings.AUTH_USER_MODEL)),
                ("etapa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="historicos", to="acompanhamento_sistemas.etapasistema")),
            ],
            options={"ordering": ["-criado_em", "-id"], "verbose_name": "Historico da etapa", "verbose_name_plural": "Historicos da etapa"},
        ),
        migrations.CreateModel(
            name="InteressadoSistema",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_interessado", models.CharField(choices=[("DEV", "Dev"), ("GESTAO", "Gestao"), ("NEGOCIO", "Negocio")], max_length=20)),
                ("nome_snapshot", models.CharField(max_length=255)),
                ("email_snapshot", models.EmailField(blank=True, max_length=254)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="interessados_sistema_criados", to=settings.AUTH_USER_MODEL)),
                ("sistema", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="interessados", to="acompanhamento_sistemas.sistema")),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="interesses_em_sistemas", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["nome_snapshot", "id"], "verbose_name": "Interessado do sistema", "verbose_name_plural": "Interessados do sistema", "unique_together": {("sistema", "usuario", "tipo_interessado")}},
        ),
        migrations.CreateModel(
            name="InteressadoSistemaManual",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_interessado", models.CharField(choices=[("DEV", "Dev"), ("GESTAO", "Gestao"), ("NEGOCIO", "Negocio")], max_length=20)),
                ("nome", models.CharField(max_length=255)),
                ("email", models.EmailField(max_length=254)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="interessados_manuais_sistema_criados", to=settings.AUTH_USER_MODEL)),
                ("sistema", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="interessados_manuais", to="acompanhamento_sistemas.sistema")),
            ],
            options={"ordering": ["nome", "id"], "verbose_name": "Interessado manual do sistema", "verbose_name_plural": "Interessados manuais do sistema", "unique_together": {("sistema", "email", "tipo_interessado")}},
        ),
        migrations.CreateModel(
            name="AnexoHistoricoEtapa",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("arquivo", models.FileField(upload_to="acompanhamento_sistemas/anexos/")),
                ("nome_original", models.CharField(blank=True, default="", max_length=255)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("historico", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="anexos", to="acompanhamento_sistemas.historicoetapasistema")),
            ],
            options={"ordering": ["id"], "verbose_name": "Anexo do historico", "verbose_name_plural": "Anexos do historico"},
        ),
    ]
