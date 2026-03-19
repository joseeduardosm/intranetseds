from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("licitacoes", "0005_itemsessao_enum_tipo"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EtpTic",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(blank=True, max_length=180, verbose_name="Titulo")),
                ("numero_processo_servico", models.CharField(max_length=120, verbose_name="Numero do processo servico")),
                ("status", models.CharField(choices=[("RASCUNHO", "Rascunho"), ("CONCLUIDO", "Concluido")], default="RASCUNHO", max_length=20)),
                ("secao_atual", models.PositiveIntegerField(default=1)),
                ("descricao_necessidade", models.TextField(blank=True)),
                ("area_requisitante", models.CharField(blank=True, max_length=180)),
                ("responsavel_area", models.CharField(blank=True, max_length=180)),
                ("necessidades_negocio", models.TextField(blank=True)),
                ("necessidades_tecnologicas", models.TextField(blank=True)),
                ("demais_requisitos", models.TextField(blank=True)),
                ("estimativa_demanda", models.TextField(blank=True)),
                ("levantamento_solucoes", models.TextField(blank=True)),
                ("analise_comparativa_solucoes", models.TextField(blank=True)),
                ("solucoes_inviaveis", models.TextField(blank=True)),
                ("analise_comparativa_custos_tco", models.TextField(blank=True)),
                ("descricao_solucao_tic", models.TextField(blank=True)),
                ("estimativa_custo_valor", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("estimativa_custo_texto", models.TextField(blank=True)),
                ("justificativa_tecnica", models.TextField(blank=True)),
                ("justificativa_economica", models.TextField(blank=True)),
                ("beneficios_contratacao", models.TextField(blank=True)),
                ("providencias_adotadas", models.TextField(blank=True)),
                ("declaracao_viabilidade", models.TextField(default="Esta equipe de planejamento declara viavel esta contratacao.")),
                ("justificativa_viabilidade", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="etps_tic_atualizados", to=settings.AUTH_USER_MODEL)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="etps_tic_criados", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-atualizado_em", "-id"],
            },
        ),
    ]
