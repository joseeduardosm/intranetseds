from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('ramais', '0003_pessoaramal_superior'),
    ]

    operations = [
        migrations.AddField(
            model_name='pessoaramal',
            name='bio',
            field=models.TextField(blank=True),
        ),
    ]
