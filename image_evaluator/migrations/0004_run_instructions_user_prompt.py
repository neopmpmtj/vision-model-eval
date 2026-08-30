from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("image_evaluator", "0003_evaluationrun_description"),
    ]

    operations = [
        migrations.RenameField(
            model_name="evaluationrun",
            old_name="prompt",
            new_name="user_prompt",
        ),
        migrations.AlterField(
            model_name="evaluationrun",
            name="user_prompt",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="evaluationrun",
            name="instructions",
            field=models.TextField(blank=True, default=""),
        ),
    ]
