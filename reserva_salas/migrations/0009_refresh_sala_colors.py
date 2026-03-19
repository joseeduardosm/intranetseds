from django.db import migrations


NEW_COLORS = [
    "#1D4ED8",
    "#0F766E",
    "#7C3AED",
    "#B45309",
    "#BE185D",
    "#166534",
    "#C2410C",
    "#334155",
    "#0891B2",
    "#4F46E5",
    "#0369A1",
    "#15803D",
    "#A21CAF",
    "#9A3412",
    "#1E40AF",
    "#6D28D9",
    "#0E7490",
    "#854D0E",
    "#BE123C",
    "#14532D",
]


def refresh_sala_colors(apps, schema_editor):
    Sala = apps.get_model("reserva_salas", "Sala")
    salas = list(Sala.objects.all().order_by("id"))
    for idx, sala in enumerate(salas):
        sala.cor = NEW_COLORS[idx % len(NEW_COLORS)]
        sala.save(update_fields=["cor"])


class Migration(migrations.Migration):
    dependencies = [
        ("reserva_salas", "0008_add_videowall"),
    ]

    operations = [
        migrations.RunPython(refresh_sala_colors, migrations.RunPython.noop),
    ]
