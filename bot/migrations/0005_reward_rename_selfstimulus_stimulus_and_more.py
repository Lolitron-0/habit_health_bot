# Generated by Django 4.2.3 on 2023-08-14 20:45

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bot', '0004_userpost'),
    ]

    operations = [
        migrations.CreateModel(
            name='Reward',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('photo_id', models.CharField(max_length=250, verbose_name='ID фото в базе телеграма')),
                ('text', models.TextField(verbose_name='Текст')),
                ('reward', models.URLField(verbose_name='Ссылка на награду')),
            ],
        ),
        migrations.RenameModel(
            old_name='SelfStimulus',
            new_name='Stimulus',
        ),
        migrations.DeleteModel(
            name='SelfReward',
        ),
        migrations.AlterModelOptions(
            name='basepost',
            options={'verbose_name': 'Привычка (База)', 'verbose_name_plural': 'Привычки (База)'},
        ),
        migrations.AlterModelOptions(
            name='defaultschedule',
            options={'verbose_name': 'Расписание для привычки (Виталия)', 'verbose_name_plural': 'Расписание для привычки (Виталия)'},
        ),
        migrations.AlterModelOptions(
            name='notification',
            options={'verbose_name': 'Уведомления пользователя', 'verbose_name_plural': 'Уведомления пользователя'},
        ),
        migrations.AlterModelOptions(
            name='post',
            options={'verbose_name': 'Привычка (Виталия)', 'verbose_name_plural': 'Привычки (Виталия)'},
        ),
        migrations.AlterModelOptions(
            name='sub',
            options={'verbose_name': 'Привычка-Пользователь', 'verbose_name_plural': 'Привычка-Пользователь (смежная)'},
        ),
        migrations.AlterModelOptions(
            name='userpost',
            options={'verbose_name': 'Привычка (Кастомная)', 'verbose_name_plural': 'Привычки (Кастомная)'},
        ),
        migrations.AlterModelOptions(
            name='userschedule',
            options={'verbose_name': 'Утро День Вечер', 'verbose_name_plural': 'Время дня пользователя'},
        ),
        migrations.RemoveField(
            model_name='mailing',
            name='media',
        ),
        migrations.RemoveField(
            model_name='post',
            name='media',
        ),
        migrations.RemoveField(
            model_name='post',
            name='video',
        ),
        migrations.AddField(
            model_name='mailing',
            name='media_id',
            field=models.CharField(blank=True, max_length=250, null=True, verbose_name='Медиа ID'),
        ),
        migrations.AddField(
            model_name='mailing',
            name='media_type',
            field=models.CharField(choices=[('P', 'Фото'), ('V', 'Видео'), ('B', 'Нет медиа')], default=1, max_length=1, verbose_name='Тип Медиа'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='post',
            name='media_id',
            field=models.CharField(blank=True, max_length=250, null=True, verbose_name='ID фото в БД телеграмма'),
        ),
        migrations.AlterField(
            model_name='post',
            name='video_id',
            field=models.CharField(blank=True, max_length=250, null=True, verbose_name='ID видео в БД телеграмма'),
        ),
        migrations.CreateModel(
            name='LevelReward',
            fields=[
                ('reward_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='bot.reward')),
                ('level_required', models.IntegerField(verbose_name='Требуемый уровень')),
            ],
            options={
                'verbose_name': 'Level Награда',
                'verbose_name_plural': 'Level Награды',
            },
            bases=('bot.reward',),
        ),
        migrations.CreateModel(
            name='TagReward',
            fields=[
                ('reward_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='bot.reward')),
                ('score_required', models.IntegerField(verbose_name='Требуемое количество выполнений')),
                ('tag', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bot.tag', verbose_name='Тэг')),
            ],
            options={
                'verbose_name': 'Tag Награда',
                'verbose_name_plural': 'Tag Награды',
            },
            bases=('bot.reward',),
        ),
        migrations.AddField(
            model_name='user',
            name='level_rewards',
            field=models.ManyToManyField(to='bot.levelreward', verbose_name='Level награды'),
        ),
        migrations.AddField(
            model_name='user',
            name='tag_rewards',
            field=models.ManyToManyField(to='bot.tagreward', verbose_name='Tag награды'),
        ),
    ]