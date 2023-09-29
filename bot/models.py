import asyncio
import datetime
import json
import logging

from django.db.models import Q
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from django.utils import timezone

from django.db import models
from django.urls import reverse
from django.contrib.contenttypes.models import ContentType
from django.utils.html import mark_safe
from django.utils.translation import gettext_lazy as _

from .utils import *

from asgiref.sync import sync_to_async, async_to_sync

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, helpers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

DEFAULT_PHOTO = "AgACAgIAAxkBAAIL2GThx4GLh0yD0qWtWpedFjWvl8dwAAI1zjEbCoIIS6FJKxT1tcASAQADAgADeQADMAQ"


class DayTimeChoices(models.TextChoices):
    MORNING = "M", _("Утро")
    NOON = "N", _("День")
    EVENING = "E", _("Вечер")


class WeekDay(models.TextChoices):
    MONDAY = "Понедельник", _("Понедельник")
    TUESDAY = "Вторник", _("Вторник")
    WEDNESDAY = "Среда", _("Среда")
    THURSDAY = "Четверг", _("Четверг")
    FRIDAY = "Пятница", _("Пятница")
    SATURDAY = "Суббота", _("Суббота")
    SUNDAY = "Воскресенье", _("Воскресенье")


class User(models.Model):
    class Gender(models.TextChoices):
        MALE = "Мужской", _("Мужской")
        FEMALE = "Женский", _("Женский")

    external_id = models.PositiveBigIntegerField(primary_key=True, unique=True, verbose_name="Telegram id")
    nickname = models.CharField(max_length=500, null=True, blank=True, verbose_name="TG nickname")
    score = models.IntegerField(default=0, verbose_name="Опыт")
    is_admin = models.BooleanField(default=False, verbose_name="Админ")
    is_signed_up = models.BooleanField(default=False, verbose_name="Зарегистрирован ли")
    first_name = models.CharField(max_length=255, verbose_name="Имя")
    last_name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Фамилия")
    sex = models.CharField(max_length=7, choices=Gender.choices, default="Мужской", blank=True, null=True,
                           verbose_name="Пол")
    age = models.SmallIntegerField(null=True, blank=True, default=0, verbose_name="Возраст")
    tz_delta = models.IntegerField(default=0, blank=True, null=True, verbose_name="Разница во времени")
    sign_up_date = models.DateTimeField(auto_now_add=True, verbose_name="Дата регистрации")
    is_subscribed = models.BooleanField(default=False, verbose_name="Подписан на канал")
    inviter = models.ForeignKey("User", on_delete=models.CASCADE, related_name="refs", null=True, blank=True,
                                verbose_name="Пригласитель")
    posts = models.ManyToManyField("BasePost", through="Sub", related_name="user_subscriptions",
                                   verbose_name="Привычки пользователя")
    sub_tags = models.ManyToManyField("Tag", blank=True, related_name="sub_users", verbose_name="Подписки на тэги")
    level_rewards = models.ManyToManyField("LevelReward", blank=True, related_name="users",
                                           verbose_name="Level награды")
    tag_rewards = models.ManyToManyField("TagReward", blank=True, related_name="users", verbose_name="Tag награды")

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        s = self.first_name
        if self.last_name:
            s += f" {self.last_name}"
        if self.sex:
            s += f", {self.get_sex_display()}"
        if self.age:
            s += f", {self.age} y.o."
        return s

    def save(self, *args, **kwargs):
        super(User, self).save(*args, **kwargs)

    def post_list(self):
        return self.posts.all()

    def tag_list(self):
        return ' / '.join([tag.__str__() for tag in self.sub_tags.all()])

    async def aget_sub_tags(self):
        tags = []
        async for tag in self.sub_tags.all():
            tags.append(tag)
        return tags

    async def aget_posts(self):
        posts = []
        async for post in self.posts.all():
            posts.append(post)
        return posts

    async def aget_subs(self):
        subs = []
        async for sub in self.subs.all().order_by("post"):
            subs.append(sub)
        return subs

    async def get_referal_link(self, bot: Bot):
        return f't.me/{(await bot.get_me())["username"]}?start={self.external_id}'

    async def check_level_rewards(self):
        logging.info(f"Checking {self.nickname} rewards...")
        level_rewards = LevelReward.objects.exclude(
            Q(level_required__gt=self.__get_level()) | Q(users__in=[self, ]))
        async for reward in level_rewards:
            await sync_to_async(self.level_rewards.add)(reward)
            logging.info(f"{reward} added to {self.nickname}")
        return level_rewards

    async def update_tag_rewards(self):
        tag_rewards = []
        async for reward in TagReward.objects.exclude(users__in=[self, ]):
            score, created = await self.get_tag_reward_score(reward)
            if created:
                tag_rewards.append(reward)
        return tag_rewards

    def get_sub_tags(self):
        return self.sub_tags

    def get_utc(self):
        SERVER_UTC = 3
        try:
            return '+' + str(
                self.tz_delta // 60 + SERVER_UTC) + " UTC" if self.tz_delta // 60 + SERVER_UTC >= 0 else str(
                self.tz_delta // 60 + SERVER_UTC) + " UTC"
        except:
            return "Пусто"

    async def get_delta_trial_period(self):
        now = datetime.datetime.now()
        return 24 * 60 * 60 - int(now.timestamp() - self.sign_up_date.timestamp())

    async def has_trial_period(self):
        return (await self.get_delta_trial_period()) > 0

    async def get_level(self):
        return self.score // 50 + 1

    def __get_level(self):
        return self.score // 50 + 1

    async def get_level_progress(self):
        from math import ceil
        return f"(🌱{self.score}/{ceil(self.score / 50) * 50})"

    def get_tag_rewards(self):
        return self.tag_rewards.all()

    def get_level_rewards(self):
        return self.level_rewards.all()

    async def get_tag_reward_score(self, reward: "TagReward"):
        t = await reward.aget_tag()
        tags = await Tag.get_structure_tag_list(t)
        tags.append(t)

        score = 0
        for tag in tags:
            async for post in tag.posts.all():
                try:
                    sub = await Sub.objects.aget(user=self, post=post)
                    score += sub.score
                except:
                    logging.info(f"{self} {post} Sub Does not exist")

        logging.info(f"Updating tag reward <{reward}> to <{self.nickname}>, score: {score}")

        if score >= reward.score_required:
            await sync_to_async(self.tag_rewards.add)(reward)

        return score, score >= reward.score_required


class UserSchedule(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="Пользователь", related_name="schedule")
    morning = models.TimeField(default=datetime.time(hour=7), verbose_name="Утро")
    noon = models.TimeField(default=datetime.time(hour=13), verbose_name="День")
    evening = models.TimeField(default=datetime.time(hour=18), verbose_name="Вечер")

    class Meta:
        verbose_name = "Утро День Вечер"
        verbose_name_plural = "Время дня пользователя"


class Tag(models.Model):
    name = models.CharField(max_length=255, verbose_name="Имя тэга")
    parent = models.ForeignKey("Tag", related_name="children", on_delete=models.CASCADE, null=True, blank=True,
                               verbose_name="Родительский тэг")
    level = models.SmallIntegerField(default=1, verbose_name="Уровень в иерархии")

    class Meta:
        verbose_name = "Тэг в иерархии"
        verbose_name_plural = "Иерархия"
        ordering = ("name",)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        level = 1
        current_tag = self
        while current_tag.parent:
            current_tag = current_tag.parent
            level += 1
        self.level = level
        super(Tag, self).save(*args, **kwargs)

    def get_admin_url(self):
        content_type = ContentType.objects.get_for_model(self.__class__)
        return reverse("admin:%s_%s_change" % (content_type.app_label, content_type.model), args=(self.name,))

    async def aget_posts(self):
        posts = []
        async for post in Post.objects.filter(tags__in=[self]):
            posts.append(post)
        return posts

    async def aget_children(self):
        children = []
        async for child in Tag.objects.filter(parent=self):
            children.append(child)
        return children

    @staticmethod
    async def get_structure_posts_count(tag):
        cnt = len(await tag.aget_posts())
        for children in await tag.aget_children():
            cnt += await Tag.get_structure_posts_count(children)
        return cnt

    @staticmethod
    async def __tag_recursion(tag, l):
        async for c in tag.children.all():
            l.append(c)
        async for child in tag.children.all():
            await Tag.__tag_recursion(child, l)
        return l

    @staticmethod
    async def get_structure_tag_list(tag):
        l = list()
        await Tag.__tag_recursion(tag, l)
        return l


class BasePost(models.Model):
    title = models.CharField(max_length=255, verbose_name="Заголовок поста", blank=True, null=True)
    score = models.SmallIntegerField(default=5, verbose_name="Очки за выполнение")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    lead_time = models.SmallIntegerField(default=180, verbose_name="Время выполнения (секунды)")
    is_bot_habit = models.BooleanField(default=True, verbose_name="Привычка Виталия (флаг)")

    class Meta:
        verbose_name = "Привычка (База)"
        verbose_name_plural = "Привычки (База)"
        ordering = ("-is_bot_habit",)

    def __str__(self):
        return f"{self.pk}{self.title}"

    async def get_lead_minute(self):
        return self.lead_time // 60

    async def get_lead_sec(self):
        return self.lead_time % 60


class Post(BasePost):
    description = models.TextField(blank=True, null=True, verbose_name="Краткое описание")
    technique = models.TextField(blank=True, null=True, verbose_name="📝 Техника выполнения ⚙️")
    benefits = models.TextField(blank=True, null=True, verbose_name="🌱 Польза 🌳")
    relevance = models.TextField(blank=True, null=True, verbose_name="🔥 Актуальность 📣")
    req_time = models.TextField(blank=True, null=True, verbose_name="🕰 Рекомендованное время 🗓")
    reqs = models.TextField(blank=True, null=True, verbose_name="👍 Рекомендации 💡")
    media_id = models.CharField(default=DEFAULT_PHOTO, max_length=250, blank=True,
                                verbose_name="ID фото в БД телеграмма")
    video_id = models.CharField(max_length=250, null=True, blank=True, verbose_name="ID видео в БД телеграмма")
    tags = models.ManyToManyField("Tag", blank=True, related_name="posts", verbose_name="Тэги")
    order_place = models.SmallIntegerField(default=1, verbose_name="Порядок в очереди")

    class Meta:
        verbose_name = "Привычка (Виталия)"
        verbose_name_plural = "Привычки (Виталия)"
        ordering = ("tags__name", "order_place")

    def subs_count(self):
        return self.subs.count()

    async def aget_schedule(self):
        items = []
        async for item in self.schedule.all():
            items.append(item)
        return items

    def tags_str(self):
        return " | ".join([t.name for t in self.tags.all()])

    """async def get_post_photo(self):
        if self.media_id:
            return self.media_id
        from telegram import Bot
        bot = Bot(token=os.environ["BOT_TOKEN"])
        my_chat_id = 532044292
        msg = await bot.sendPhoto(chat_id=my_chat_id, photo=self.media.path)
        self.media_id = msg.photo[-1].file_id
        await self.asave()
        return self.media_id

    async def get_post_video(self):
        bot = Bot(token=os.environ["BOT_TOKEN"])
        if self.video_id:
            return self.video_id
        my_chat_id = 532044292
        msg = await bot.sendVideo(chat_id=my_chat_id, video=self.video.path)
        self.video_id = msg.video.file_id
        await self.asave()
        return self.video_id"""


@receiver(m2m_changed, sender=Post.tags.through)
def m2m_changed_post(sender, instance, action, **kwargs):
    for user in User.objects.all():
        for tag in user.sub_tags.all():
            if tag in instance.tags.all():
                asyncio.run(send_notification_post(user, instance, tag))


class UserPost(BasePost):
    aim = models.TextField(blank=True, null=True, verbose_name="Цель")
    reward1 = models.TextField(blank=True, null=True, verbose_name="Награда за 1-кратное выполнение")
    reward30 = models.TextField(blank=True, null=True, verbose_name="Награда за 30-кратное выполнение")

    class Meta:
        verbose_name = "Привычка (Кастомная)"
        verbose_name_plural = "Привычки (Кастомная)"


class DefaultSchedule(models.Model):
    weekday = models.CharField(max_length=15, choices=WeekDay.choices, null=True, blank=True,
                               verbose_name="День недели")
    daytime = models.CharField(max_length=50, null=True, blank=True, choices=DayTimeChoices.choices,
                               verbose_name="Время дня")
    time = models.TimeField(null=True, blank=True, verbose_name="Время выполнения")
    post = models.ForeignKey("Post", related_name="schedule", on_delete=models.CASCADE,
                             verbose_name="Ссылка на привычку")

    class Meta:
        verbose_name = "Расписание для привычки (Виталия)"
        verbose_name_plural = "Расписание для привычки (Виталия)"

    def __str__(self):
        return f"{self.get_post()}"

    def get_post(self):
        return self.post

    async def aget_post(self):
        return await Post.objects.filter(schedule__in=[self]).afirst()


class Notification(models.Model):
    # week_days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    daytime = models.CharField(max_length=50, null=True, blank=True, choices=DayTimeChoices.choices,
                               verbose_name="Время дня")
    sub = models.ForeignKey("Sub", related_name="notifications", on_delete=models.CASCADE,
                            verbose_name="Привычка пользователя")

    class Meta:
        verbose_name = "Уведомления пользователя"
        verbose_name_plural = "Уведомления пользователя"

    def __str__(self):
        return f"{self.pk}"

    def get_user(self):
        return self.sub.user

    def get_post(self):
        return self.sub.post

    async def aget_sub(self):
        return await Sub.objects.filter(notifications__in=[self]).afirst()


class Sub(models.Model):
    user = models.ForeignKey("User", on_delete=models.CASCADE, related_name="subs", verbose_name="Пользователь")
    post = models.ForeignKey("BasePost", on_delete=models.CASCADE, related_name="subs", verbose_name="Пост")
    score = models.IntegerField(default=0, verbose_name="Счёт выполнения")

    class Meta:
        verbose_name = "Привычка-Пользователь"
        verbose_name_plural = "Привычка-Пользователь (смежная)"

    def __str__(self):
        return f"{self.user} {self.post}"

    def save(self, *args, **kwargs):
        super(Sub, self).save(*args, **kwargs)

    async def aget_user(self) -> User:
        return await User.objects.filter(subs__in=[self]).afirst()

    async def aget_post(self) -> Post:
        return await BasePost.objects.filter(subs__in=[self]).afirst()

    async def aget_notifications(self) -> list[Notification]:
        l = []
        async for n in self.notifications.all():
            l.append(n)
        return l


class Mailing(models.Model):
    class MediaTypes(models.TextChoices):
        PHOTO = "P", _("Фото")
        VIDEO = "V", _("Видео")
        BLANK = "B", _("Нет медиа")

    media_id = models.CharField(max_length=250, null=True, blank=True, verbose_name="Медиа ID")
    media_type = models.CharField(max_length=1, choices=MediaTypes.choices, verbose_name="Тип Медиа")
    text = models.TextField(null=True, blank=True, verbose_name="Тектс сообщения")
    send_time = models.DateTimeField(default=timezone.now, verbose_name="Время отправки")

    class Meta:
        verbose_name = "Рассылка"
        verbose_name_plural = "Рассылка"

    def __str__(self):
        return self.text[:50]


class Reward(models.Model):
    name = models.CharField(max_length=250, verbose_name="Название награды")
    photo_id = models.CharField(default=DEFAULT_PHOTO, max_length=250, verbose_name="ID фото в базе телеграма")
    text = models.TextField(verbose_name="Текст")
    reward = models.URLField(blank=True, null=True, verbose_name="Ссылка на награду")

    def __str__(self):
        return self.name


class LevelReward(Reward):
    level_required = models.IntegerField(verbose_name="Требуемый уровень")

    class Meta:
        verbose_name = "Level Награда"
        verbose_name_plural = "Награды (Level)"


@receiver(post_save, sender=LevelReward)
def update_user_level_rewards(sender, instance, **kwargs):
    logging.info(f"Update level rewards, sender:{sender}, {instance}")
    for user in User.objects.all():
        async_to_sync(user.check_level_rewards)()


class TagReward(Reward):
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, verbose_name="Тэг")
    score_required = models.IntegerField(verbose_name="Требуемое количество выполнений")

    class Meta:
        verbose_name = "Tag Награда"
        verbose_name_plural = "Награды (Tag)"

    async def aget_tag(self):
        return await Tag.objects.filter(tagreward__in=[self, ]).afirst()


@receiver(post_save, sender=TagReward)
def update_user_tag_rewards(sender, instance, **kwargs):
    logging.info(f"Update tag rewards sender:{sender}, {instance}")
    for user in User.objects.all():
        async_to_sync(user.get_tag_reward_score)(reward=instance)


class Stimulus(models.Model):
    text = models.TextField(verbose_name="Текст")

    class Meta:
        verbose_name = "Стимул"
        verbose_name_plural = "Стимул"

    def __str__(self):
        return self.text[:100]
