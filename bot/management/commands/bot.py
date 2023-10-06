import functools
from copy import deepcopy

import django.db.models
import telegram

from django.core.management.base import BaseCommand
from datetime import datetime
from dotenv import load_dotenv

from .utils import *
from ...models import *

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    InputMediaPhoto, InputMedia, helpers, PhotoSize, Message, InlineQueryResultArticle, InputTextMessageContent,
    InlineQueryResultCachedPhoto,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    InlineQueryHandler,
    filters,
)

from telegram.error import BadRequest

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# load env
load_dotenv()

# getting the text of the commands
with open(os.path.dirname(__file__) + "/text_bot.json", "r", encoding="utf-8") as f:
    text = json.load(f)
    f.close()

# set static variables
AGE, SEX, UTC = range(3)
# set static for sub settings
DAY, TIME, NOTIFICATION_ADDED = range(3)
# menu static variables
ADD, POST_LIST, TAG_LIST, TODAY_HABITS, CREATE, MAIN_MENU, SCHEDULE, ACHIEVEMENTS, PROFILE_SETTINGS, SIGN_UP = "tag_id=0", "POST_LIST", "TAG_LIST", \
                                                                                                               "TODAY_HABITS", "CREATE", "MAIN_MENU", '{"daytime": "default"}', "ACHIEVEMENTS", "PROFILE_SETTINGS", "SIGN_UP"

bot = Bot(token=os.environ["BOT_TOKEN"])
application = Application.builder().token(os.environ["BOT_TOKEN"]).build()

SKIP_BUTTON_MARKUP = ReplyKeyboardMarkup([[KeyboardButton("Пропустить")]], one_time_keyboard=True)
BACK_BUTTON_TEXT = "🏃🏻Назад"
MENU_TEXT = "☰ Меню:"

button_data_list = [
    # ["video_id", "🎬 Видео 🌿"],
    ["technique", "📝 Техника выполнения ⚙️"], ["benefits", "🌱 Польза 🌳"],
    ["relevance", "🔥 Актуальность 📣"],
    ["req_time", "🕰 Рекомендованное время 🗓"], ["reqs", "👍 Рекомендации 💡"]]


async def update_or_create_user(chat: telegram.User, context: ContextTypes.DEFAULT_TYPE = None) -> (User, bool):
    if context:
        user, created = await User.objects.aupdate_or_create(external_id=chat.id, defaults={
            "first_name": chat.first_name,
            "last_name": chat.last_name,
            "nickname": chat.username,
            "is_signed_up": True,
            "sex": context.user_data["sex"],
            "age": context.user_data["age"],
            "tz_delta": context.user_data["utc"]
        })
    else:
        user, created = await User.objects.aupdate_or_create(external_id=chat.id, defaults={
            "first_name": chat.first_name,
            "last_name": chat.last_name,
            "nickname": chat.username,
        })
    if created:
        await UserSchedule.objects.acreate(user=user)
    return user, created


async def is_user_subscribed(user_id, channel_username):
    try:
        member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        return member.status in ['member', 'creator', 'administrator']
    except BadRequest:
        return False


# start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, created = await update_or_create_user(chat=update.effective_user)
    try:
        if context.args[0] and created:
            ref = int(context.args[0])
            inviter = await User.objects.aget(pk=ref)
            if user != inviter:
                user.inviter = inviter
                await user.asave()
                logging.info(f"Start new user {user}, inviter: {inviter}")
    except:
        if created:
            logging.warning(f"Start new user {user}")
    reply_markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(text="Подписаться на канал", url="https://t.me/BodnarVitaliy")],
            [InlineKeyboardButton(text="Поделиться c близкими",
                                  url=f"https://telegram.me/share/url?url={await user.get_referal_link(bot)}&text=Подпишись по моей реферальной ссылке чтобы получить день пробного периода!")],
            [InlineKeyboardButton(text="Проверить условия", callback_data="check_requirements")],
            [InlineKeyboardButton(text="Зарегистрироваться", callback_data=SIGN_UP)]
        ]
    )
    await update.message.reply_text(f'{text["start"]}', reply_markup=reply_markup, parse_mode="HTML")


async def share_ref_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = await User.objects.aget(external_id=update.effective_user.id)
    await query.answer(text=(await user.get_referal_link(bot)), show_alert=True)


async def check_requirements_by_user(user):
    if await is_user_subscribed(user.external_id, "@BodnarVitaliy"):
        user.is_subscribed = True
    else:
        user.is_subscribed = False
    await user.asave()
    cnt = 0
    async for ref_user in user.refs.all():
        if await is_user_subscribed(ref_user.external_id, "@BodnarVitaliy"):
            cnt += 1
    return user.is_subscribed, cnt


async def check_requirements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = await User.objects.aget(external_id=update.effective_user.id)
    reply_text = str()
    if user.is_admin:
        reply_text += "Вы админ, кайфуйте"
    else:
        is_subscribed, cnt = await check_requirements_by_user(user)
        smile_subscribed = "🌳" if is_subscribed else "🌱"
        reply_text += f"🙏🏻 Подписка на автора: {smile_subscribed}\n"
        smile_cnt = "🌳" if cnt >= 2 else "🌱"
        reply_text += f"👥 Поделись с другими: {cnt}/2 {smile_cnt}\n"
        has_trial = await user.has_trial_period()
        if has_trial:
            reply_text += f"⏳ Пробный период: {(await user.get_delta_trial_period()) // 3600} ч."
        else:
            reply_text += f"⏳ Пробный период: Истёк"
    await bot.sendMessage(chat_id=update.effective_user.id, text=reply_text)


def requirements_required(func):
    @functools.wraps(func)
    async def decorator(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            user = await User.objects.aget(external_id=update.effective_user.id)
            if not user.is_admin and not (await user.has_trial_period()):
                is_subscribed, cnt = await check_requirements_by_user(user)
                if not is_subscribed or cnt < 2:
                    reply_text = "Проверьте условия: 1) Вы подписаны на канал @BodnarVitaliy 2) Вы пригласили 2 друзей в этого бота"
                    reply_markup = InlineKeyboardMarkup(
                        [[InlineKeyboardButton(text="Проверить условия", callback_data="check_requirements")]])
                    await bot.sendMessage(chat_id=user.external_id, text=reply_text, reply_markup=reply_markup)
                    return
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            logging.info(e)
            await bot.sendMessage(chat_id=update.effective_user.id, text="Сначала нажмите /start")

    return decorator


def sign_up_required(func):
    @functools.wraps(func)
    async def decorator(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            user = await User.objects.aget(external_id=update.effective_user.id)
            if not user.is_signed_up:
                await bot.sendMessage(chat_id=update.effective_user.id, text="Сначала зарегистрируйтесь /sign_up")
                return
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            logging.warning(e)
            await bot.sendMessage(chat_id=update.effective_user.id, text="Сначала нажмите /start")

    return decorator


@requirements_required
async def sign_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    chat = update.effective_user
    reply_keyboard = [["Мужской", "Женский", "Пропустить"]]
    await bot.sendMessage(chat_id=chat.id, text=text["input sex"], reply_markup=ReplyKeyboardMarkup(
        reply_keyboard, one_time_keyboard=True, input_field_placeholder="Выберите ваш пол"))
    return SEX


async def get_sex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sex"] = update.message.text
    await update.message.reply_text(text["input age"], reply_markup=SKIP_BUTTON_MARKUP)
    return AGE


async def skip_sex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sex"] = None
    await update.message.reply_text(text["input age"], reply_markup=SKIP_BUTTON_MARKUP)
    return AGE


async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    age = update.message.text
    if age.isdigit() and 0 <= int(age) <= 150:
        context.user_data["age"] = int(age)
        await update.message.reply_text(text=text["input utc"], reply_markup=SKIP_BUTTON_MARKUP)
        return UTC
    else:
        await update.message.reply_text("Введите число!")


async def skip_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["age"] = None
    await update.message.reply_text(text=text["input utc"])
    return UTC


async def get_utc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    chat = update.effective_user
    try:
        hour, minute = map(int, message.split(":"))
        abs_min = hour * 60 + minute
        server_h, server_m = datetime.datetime.now().hour, datetime.datetime.now().minute
        server_m = server_h * 60 + server_m
        delta = abs_min - server_m
        context.user_data["utc"] = delta
        await update_or_create_user(chat, context)
        await update.message.reply_text(text["reg ended"], reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text(text=MENU_TEXT, reply_markup=await get_main_menu())
        return ConversationHandler.END
    except Exception as e:
        logging.warning(e)
        await update.message.reply_text("Что то пошло не так! " + text["input utc"], reply_markup=SKIP_BUTTON_MARKUP)
        return UTC


async def skip_utc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["utc"] = None
    chat = update.effective_user
    await update_or_create_user(chat, context)
    await update.message.reply_text(text["reg ended"])
    return ConversationHandler.END


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(text["help"])


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    await update.message.reply_text(
        text["cancel text"], reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


async def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("🧘🏻 Выбрать упражнение-привычку", callback_data=ADD)],
        [InlineKeyboardButton("🌱 Создать свою привычку", callback_data=CREATE)],
        [InlineKeyboardButton("✨ Мои привычки", callback_data=POST_LIST)],
        [InlineKeyboardButton("🎁 Мои достижения", callback_data=ACHIEVEMENTS)],
        [InlineKeyboardButton("📝 Моё расписание на сегодня", callback_data=TODAY_HABITS)],
        [InlineKeyboardButton("🕰 Ожидаемые привычки", callback_data=TAG_LIST)],
        [InlineKeyboardButton("⚙️ Настройки профиля", callback_data=PROFILE_SETTINGS)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return reply_markup


async def get_inline_schedule(field_name, user_sch):
    d = {"morning": "Утро", "noon": "День", "evening": "Вечер"}
    daytime = getattr(user_sch, field_name)
    l = []
    if daytime.hour > 0:
        minus = json.dumps({"daytime": field_name, "value": str(daytime.hour - 1)})
        l.append(InlineKeyboardButton(text="◀️", callback_data=minus))
    if daytime.hour < 23:
        plus = json.dumps({"daytime": field_name, "value": str(daytime.hour + 1)})
        l.append(InlineKeyboardButton(text="▶️", callback_data=plus))
    l.insert(1, InlineKeyboardButton(text=f"{d[field_name]} {daytime.hour}:00",
                                     callback_data="zaglushka"))
    return l


async def zaglushka(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer(text="Настраивайте расписание нажимая кнопки по бокам ⚙️")


async def user_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = json.loads(query.data)

    reply_text = "Ваше расписание: "
    user_sch: UserSchedule = await UserSchedule.objects.aget(user__external_id=update.effective_user.id)
    if data["daytime"] != "default":
        setattr(user_sch, data["daytime"], datetime.time(hour=int(data["value"])))
        await user_sch.asave()

    keyboard = []
    for daytime in ("morning", "noon", "evening"):
        keyboard.append(await get_inline_schedule(daytime, user_sch))

    keyboard.append([InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=PROFILE_SETTINGS)])

    try:
        await query.edit_message_text(text=reply_text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logging.info(e)
        await query.delete_message()
        await bot.sendMessage(chat_id=update.effective_user.id, text=reply_text,
                              reply_markup=InlineKeyboardMarkup(keyboard))


@requirements_required
@sign_up_required
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user = await User.objects.aget(external_id=update.effective_user.id)
    reply_markup = None
    if user:
        reply_markup = await get_main_menu()
        answer = MENU_TEXT
    else:
        answer = text["register please"]
    await bot.sendMessage(chat_id=update.effective_user.id, text=answer, reply_markup=reply_markup)


async def main_menu_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    reply_markup = await get_main_menu()
    try:
        await query.message.edit_text(text=MENU_TEXT, reply_markup=reply_markup)
    except:
        await query.delete_message()
        await bot.sendMessage(chat_id=update.effective_user.id, text=MENU_TEXT, reply_markup=reply_markup)


async def posts_to_dict(posts: list[Tag]) -> dict:
    d = dict()
    num = 1
    for post in posts:
        d[num] = post
        num += 1
    return d


async def posts_to_text(posts: dict) -> str:
    reply_text = "\nНайденные привычки:\n"
    """for item in posts.items():
        post: Post = item[1]
        reply_text += f"{item[0]}) {post.title}\n"
        reply_text += f"{post.description}\n\n"""
    return reply_text


async def posts_to_keyboard(keyboard: list, posts: list[Post]) -> list:
    """index = 0
    while index < len(posts):
        keyboard.append([InlineKeyboardButton(f"🟩 Добавить {post.title}", callback_data=f"add_post={post.pk}") for post in
                         posts[index: min(index + 4, len(posts))]])
        index += 4"""
    for post in posts:
        cb_data = json.dumps({"pc": post.pk, "e": False})
        keyboard.append(
            [InlineKeyboardButton(f"{post.title}", callback_data=cb_data)])
    return keyboard


async def tag_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = []
    current_tag = None
    tags = []
    related_posts = []
    posts_text = str()
    data = query.data

    # if level of the posts == 1
    if data == ADD:
        warning_text = text["planning"]
        async for tag in Tag.objects.filter(level=1):
            tags.append(tag)
        back_button = [InlineKeyboardButton(BACK_BUTTON_TEXT, callback_data=MAIN_MENU)]
    else:
        current_tag = await Tag.objects.aget(pk=int(data.split("=")[1]))

        warning_text = f"☰ {current_tag.name}\n\n"
        async for ch in current_tag.children.all():
            tags.append(ch)

        # back button
        parent_tag = await Tag.objects.filter(children=current_tag).afirst()
        if parent_tag:
            back_button = [InlineKeyboardButton(BACK_BUTTON_TEXT, callback_data=f"tag_id={parent_tag.pk}")]
        else:
            back_button = [InlineKeyboardButton(BACK_BUTTON_TEXT, callback_data=ADD)]

    # adding all related tags to keyboard
    """index = 0
    while index < len(tags):
        keyboard.append([InlineKeyboardButton(f"🟦 {tag.name}", callback_data=f"tag_id={tag.pk}") for tag in
                         tags[index: min(index + 2, len(tags))]])
        index += 2"""

    if current_tag and current_tag.level != 2 and not await Tag.get_structure_posts_count(current_tag):
        warning_text += "По этой теме еще нет привычек! Вы можете подписаться, чтобы получить уведомление!"
        # keyboard.append([InlineKeyboardButton("Подписаться", callback_data=f"subscribe_tag={tag.pk}")])
    elif current_tag and current_tag.level == 2:
        warning_text += text["waiting"]

    user = await User.objects.aget(external_id=update.effective_user.id)

    for tag in tags:
        cb_data = f"tag_id={tag.pk}"
        structure_count = await Tag.get_structure_posts_count(tag)

        if data == ADD or current_tag.level < 2:
            line = [InlineKeyboardButton(text=f"{tag.name} ({structure_count})",
                                         callback_data=cb_data)]
        else:
            if tag in await user.aget_sub_tags():
                line = [InlineKeyboardButton(text=f"{tag.name} ({structure_count})",
                                             callback_data=cb_data),
                        InlineKeyboardButton(text="✅ Ожидаю", callback_data=f"subscribe_tag={tag.pk}")
                        ]
            else:
                line = [InlineKeyboardButton(text=f"{tag.name} ({structure_count})",
                                             callback_data=cb_data),
                        InlineKeyboardButton(text="⏳ Ожидаю", callback_data=f"subscribe_tag={tag.pk}")
                        ]
        keyboard.append(line)

    if current_tag:
        # looking for related posts
        async for post in current_tag.posts.all():
            related_posts.append(post)
        if related_posts:
            d = await posts_to_dict(related_posts)
            posts_text += await posts_to_text(d)

            # add post_list
            await posts_to_keyboard(keyboard, related_posts)

    if back_button:
        keyboard.append(back_button)
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(
            text=warning_text + posts_text, reply_markup=reply_markup, parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(e)
        await query.delete_message()
        await bot.sendMessage(chat_id=update.effective_user.id, text=warning_text + posts_text,
                              reply_markup=reply_markup, parse_mode="Markdown")


async def user_tag_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat = update.effective_user
    user = await User.objects.aget(external_id=chat.id)
    keyboard = []
    async for tag in user.sub_tags.all():
        keyboard.append([InlineKeyboardButton(text=f"{tag.name}", callback_data=f"tag_id={tag.pk}"),
                         InlineKeyboardButton(text="Отписаться", callback_data=f"unsubscribe_tag={tag.pk}")])
    keyboard.append([InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=MAIN_MENU)])
    reply_market = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text="⚙️ Настройка ваших подписок:", reply_markup=reply_market)


async def subscribe_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    user = await User.objects.aget(external_id=update.effective_user.id)
    tag = await Tag.objects.aget(pk=data.split("=")[1])

    parent = await Tag.objects.filter(children=tag).afirst()

    if parent:
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=f"tag_id={parent.pk}")]])
    else:
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=ADD)]])

    if tag in await user.aget_sub_tags():
        await query.edit_message_text(
            f'Вы уже ожидаете привычки по теме "{tag.name}". Скоро я оповещу Вас о выходе упражнений по теме.',
            reply_markup=reply_markup)

    else:
        await sync_to_async(user.sub_tags.add)(tag)
        await query.edit_message_text(
            f'Вы ожидаете привычки на тему "{tag.name}". Скоро я оповещу Вас о выходе упражнений по теме.',
            reply_markup=reply_markup)


async def unsubscribe_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    tag_pk = query.data.split("=")[1]
    tag = await Tag.objects.aget(pk=tag_pk)

    user_id = update.effective_user.id
    user = await User.objects.aget(external_id=user_id)

    await sync_to_async(user.sub_tags.remove)(tag)

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=TAG_LIST)]])

    await query.edit_message_text(text=f'Вы отписались от обновлений "{tag.name}"', reply_markup=reply_markup)


async def add_post_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    post = await Post.objects.aget(pk=data.split("=")[1])
    defaults: list[DefaultSchedule] = await post.aget_schedule()

    chat = update.effective_user
    user = await User.objects.aget(external_id=chat.id)

    sub, created = await Sub.objects.aget_or_create(user=user, post=post)

    for default in defaults:
        await Notification.objects.acreate(sub=sub, day_of_week=default.weekday,
                                           daytime=default.daytime)

    if created:
        answer = f"Вы добавили привычку {post.title}"
    else:
        answer = "Вы уже добавили эту привычку"
    keyboard = [[InlineKeyboardButton(text="⚙️ Настроить привычку", callback_data=f"sub_settings={sub.pk}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await bot.sendMessage(chat_id=update.effective_user.id, text=answer, reply_markup=reply_markup)


async def post_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        data = json.loads(query.data)
        post_pk, extended = data["pc"], data["e"]
    elif len(context.args):
        post_pk, extended = context.args[0], True
    else:
        return

    try:
        post = await Post.objects.aget(pk=post_pk)
    except Exception as e:
        logging.warning(e)
        return

    try:
        user = await User.objects.aget(external_id=update.effective_user.id)
    except Exception as e:
        logging.warning(e)
        user = None

    keyboard = []

    if extended:
        for button_data in button_data_list:
            cb_data = json.dumps({"field": button_data[0], "post_pk": post.pk})
            keyboard.append([InlineKeyboardButton(text=button_data[1], callback_data=cb_data)])
    else:
        cb_data = json.dumps({"pc": post_pk, "e": True})
        keyboard.append([InlineKeyboardButton(text="💡 Видео и подробности", callback_data=cb_data)])

    if user and post.pk in [i.pk for i in await user.aget_posts()]:
        sub = await Sub.objects.filter(Q(post=post) & Q(user=user)).afirst()
        interaction_button = [
            InlineKeyboardButton(text="⚙️ Настроить привычку", callback_data=f"sub_settings={sub.pk}")]
        keyboard.append(interaction_button)
    elif user:
        interaction_button = [InlineKeyboardButton(text="🧩 Добавить", callback_data=f"add_post={post.pk}")]
        keyboard.append(interaction_button)

    if query:
        keyboard.append([InlineKeyboardButton(text=BACK_BUTTON_TEXT,
                                              callback_data=f"tag_id={(await Tag.objects.filter(posts__in=[post, ]).afirst()).pk}")])
    else:
        # TODO: make start button
        pass
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        try:
            if extended:
                await query.edit_message_media(media=InputMedia(media=post.video_id, media_type="video"))
            else:
                await query.edit_message_media(media=InputMedia(media=post.media_id, media_type="photo"))
        except Exception as e:
            logging.warning(e)
        await query.edit_message_caption(caption=post.title, reply_markup=reply_markup)
    except Exception as e:
        logging.warning(e)
        chat_id = update.effective_user.id
        if query:
            await query.delete_message()
        if post.video_id:
            video = post.video_id
            await bot.sendVideo(chat_id=chat_id, caption=post.title, video=video,
                                reply_markup=reply_markup, supports_streaming=True)
        elif post.media_id:
            photo = post.media_id
            await bot.sendPhoto(chat_id=chat_id, caption=post.title, photo=photo,
                                reply_markup=reply_markup)
        else:
            await bot.sendMessage(chat_id=chat_id, text=post.title, reply_markup=reply_markup)


async def get_post_list_by_schedule(user: User, current_hour: int) -> (list[Sub], str) or None:
    schedule: UserSchedule = await UserSchedule.objects.aget(user=user)
    user_subs = await user.aget_subs()
    daytime = None
    if current_hour == schedule.morning.hour:
        daytime = DayTimeChoices.MORNING
    elif current_hour == schedule.noon.hour:
        daytime = DayTimeChoices.NOON
    elif current_hour == schedule.evening.hour:
        daytime = DayTimeChoices.EVENING
    reply = ""
    if daytime:
        habit_list = []
        for sub in user_subs:
            for n in await sub.aget_notifications():
                if n.daytime == daytime:
                    reply = n.get_daytime_display()
                    habit_list.append(sub)
                    break
        return habit_list, reply
    return None, None


async def get_post_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    data = json.loads(query.data)
    field, post = data["field"], await Post.objects.aget(pk=data["post_pk"])
    if field == "video_id":
        value: django.db.models.CharField = getattr(post, field)
    else:
        value: django.db.models.TextField = getattr(post, field)
    field_text = f"\n{Post._meta.get_field(field_name=field).verbose_name}:\n{value}\n"

    try:
        flag = context.user_data["habit_query"]
    except:
        flag = False
    keyboard = []
    if flag:
        user = await User.objects.aget(external_id=update.effective_user.id)
        buf, _ = await get_post_list_by_schedule(user, context.user_data["habit_hour"])
        habits = [habit.pk for habit in buf]
        index = context.user_data["habit_index"]
        cb_data = {"hq": habits, "i": index, "c": False, "n": False, "e": True}
        back_button = [
            InlineKeyboardButton(BACK_BUTTON_TEXT,
                                 callback_data=f"key={await write_state(cb_data)}")]
    else:
        cb_data = json.dumps({"pc": post.pk, "e": True})
        back_button = [InlineKeyboardButton(BACK_BUTTON_TEXT, callback_data=cb_data)]
    keyboard.append(back_button)
    reply_markup = InlineKeyboardMarkup(keyboard)
    if field == "video_id":
        await query.edit_message_media(InputMedia(media_type="video", media=value))
        await query.edit_message_caption(caption=f"{post.title}", reply_markup=reply_markup, parse_mode="HTML")
    else:
        await query.edit_message_caption(caption=f"{post.title}" + field_text, reply_markup=reply_markup,
                                         parse_mode="HTML")


async def sub_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    sub = await Sub.objects.aget(pk=data.split("=")[1])
    post = await sub.aget_post()

    notification_list = []
    async for notification in sub.notifications.all():
        notification_list.append(notification)

    reply_text = f"Счёт выполнения: {sub.score}\n"

    keyboard = await get_notification_keyboard(sub)

    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(text=reply_text, reply_markup=reply_markup, parse_mode="HTML")
    except:
        await query.delete_message()
        await bot.sendMessage(chat_id=update.effective_user.id, text=reply_text, reply_markup=reply_markup,
                              parse_mode="HTML")


async def get_notification_keyboard(sub: Sub):
    keyboard = []

    post = await sub.aget_post()
    if post.is_bot_habit:
        cb_data = json.dumps({"pc": post.pk, "e": False})
        keyboard.append([InlineKeyboardButton(f"ℹ️ Информация о привычке", callback_data=cb_data)])

    d = {"M": "Утро", "N": "День", "E": "Вечер"}
    notifications = []
    for daytime in ('M', 'N', 'E'):
        notification = await Notification.objects.filter(sub=sub, daytime=daytime).afirst()
        if notification:
            notifications.append(notification)
        else:
            notifications.append(Notification(daytime=daytime, sub=sub))

    for notification in notifications:
        if notification.pk:
            cb_data = json.dumps({"dn": notification.pk})
            keyboard.append([InlineKeyboardButton(text=f"✅ {d[notification.daytime]}", callback_data=cb_data)])
        else:
            cb_data = json.dumps({"cn": notification.daytime, "s": sub.pk})
            keyboard.append([InlineKeyboardButton(text=f"❌ {d[notification.daytime]}", callback_data=cb_data)])
    keyboard += [
        [InlineKeyboardButton(f"🗑 Удалить привычку", callback_data=f"delete_sub={sub.pk}")],
        [InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=POST_LIST)]
    ]
    return keyboard


async def sub_settings_user_habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    sub = await Sub.objects.aget(pk=data.split("=")[1])

    await query.edit_message_text(
        text=f"Настройка привычки '{await sub.aget_post()}'\nСчёт выполнения: {sub.score}",
        reply_markup=InlineKeyboardMarkup(await get_notification_keyboard(sub)))


async def create_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = json.loads(query.data)
    daytime = data["cn"]
    sub = await Sub.objects.aget(pk=data["s"])
    notification = await Notification.objects.acreate(daytime=daytime, sub=sub)
    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(await get_notification_keyboard(await notification.aget_sub())))


async def delete_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = json.loads(query.data)
    notification = await Notification.objects.aget(pk=data["dn"])
    sub = await notification.aget_sub()
    await notification.adelete()
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(await get_notification_keyboard(sub)))


async def today_subs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = await User.objects.aget(external_id=update.effective_user.id)
    today_habits: list[Notification] = []
    async for habit in user.subs.all():
        async for notification in habit.notifications.all():
            today_habits.append(notification)

    today_habits.sort(key=lambda x: ["M", "N", "E"].index(x.daytime))
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=MAIN_MENU)]])

    if len(today_habits):

        reply_text = "Расписание на сегодня:\n\n"

        index = 1
        for habit in today_habits:
            sub = await habit.aget_sub()
            post = await sub.aget_post()
            reply_text += f"{index}) {post.title}\n" \
                          f"Время выполнения:  {habit.get_daytime_display()}\n\n"
            index += 1

        await query.edit_message_text(reply_text, reply_markup=reply_markup)
    else:
        await query.edit_message_text("На сегодня ничего нет!", reply_markup=reply_markup)


async def delete_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    sub = await Sub.objects.aget(pk=data.split("=")[1])

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=POST_LIST)]])

    post = await BasePost.objects.aget(subs__in=[sub])

    await query.delete_message()
    await bot.sendMessage(chat_id=update.effective_user.id,
                          text=f"Привычка {post.title} успешно удалена",
                          reply_markup=reply_markup)

    await sub.adelete()


async def set_default_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sub = await Sub.objects.aget(pk=context.user_data["sub_setting_pk"])
    post = await sub.aget_post()
    async for item in post.schedule.all():
        await Notification.objects.aget_or_create(sub=sub, time=item.time, day_of_week=item.weekday)
    await update.message.reply_text(text=text["added default"])
    return ConversationHandler.END


async def completed_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    sub = await Sub.objects.aget(pk=data.split("=")[1])

    sub.score += 1
    await sub.asave()

    post = await sub.aget_post()

    await query.edit_message_text(
        text=f'Отлично! Счет выполнения привычки "{post.title}" равен {sub.score}')


async def not_completed_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    sub = await Sub.objects.aget(pk=data.split("=")[1])

    post = await sub.aget_post()

    await query.edit_message_text(
        text=f'Счет выполнения привычки "{post.title}" равен {sub.score}. Если вам неудобно расписание, его всегда можно изменить в настройках')


async def user_post_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat = update.effective_user
    user = await User.objects.aget(external_id=chat.id)
    keyboard = []
    async for post in user.posts.all():
        sub = await Sub.objects.aget(Q(user=user) & Q(post=post))
        if post.is_bot_habit:
            keyboard.append([InlineKeyboardButton(text=f"{post.title}",
                                                  callback_data=f"sub_settings={sub.pk}")])
        else:
            keyboard.append([InlineKeyboardButton(text=f"{post.title}\n",
                                                  callback_data=f"user_sub_settings={sub.pk}")])
    keyboard.append([InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=MAIN_MENU)])
    reply_market = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(text="Настройка ваших привычек:", reply_markup=reply_market)
    except:
        await bot.sendMessage(chat_id=update.effective_user.id, text="Настройка ваших привычек:",
                              reply_markup=reply_market)
    return ConversationHandler.END


async def remove_job(name, context: ContextTypes.DEFAULT_TYPE):
    jobs = context.job_queue.get_jobs_by_name(name)
    for job in jobs:
        job.schedule_removal()


async def callback_hour(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.sendMessage(context.job.chat_id, text=text["callback hour"])


async def callback_3hours(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.sendMessage(context.job.chat_id, text=text["callback 3 hours"])


async def callback_timer(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    post, completed = data["post"], data["completed"]
    current_message: Message = data["cm"]
    try:
        keyboard: list = list(current_message.reply_markup.inline_keyboard)
        for i in range(1, post.lead_time // 2, 1):
            current_message = await bot.edit_message_text(chat_id=context.job.chat_id, message_id=current_message.id,
                                                          text=current_message.text)
            keyboard: list = list(current_message.reply_markup.inline_keyboard)
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton(text=f"({post.lead_time // 2 - i} сек) Выполнил(а) ✅",
                                       callback_data="com_zag")]] + keyboard[1:])
            current_message = await bot.edit_message_reply_markup(message_id=current_message.id,
                                                                  reply_markup=reply_markup,
                                                                  chat_id=context.job.chat_id)
            await asyncio.sleep(1)
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text=f"Выполнил(а) ✅",
                                                                   callback_data={
                                                                       await write_state(completed)})]] + keyboard[
                                                                                                          1:])
        await current_message.edit_reply_markup(reply_markup)
    except Exception as e:
        logging.warning(e)


async def habit_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = await User.objects.aget(external_id=update.effective_user.id)

    async with async_open(os.path.dirname(__file__) + "/states.json", "r", encoding="utf-8") as f:
        state_id = query.data.split("=")[1]
        data = json.loads(await f.read())[state_id]
        await delete_state(state_id)
    logging.info(f"CALLBACK DATA: {data}")
    habit_list, index, new_message, is_extended, is_com = data["hq"], data["i"], data["n"], data["e"], data["c"]
    if index == 0:
        if not data["e"]:
            await query.delete_message()
        context.user_data["score"] = 0

    if new_message and index != 0:
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                text="Выполнено  ✅" if is_com else "Не выполнено ❌", callback_data="zaglushka_hq")]]))

    context.user_data["habit_query"] = True
    context.user_data["habit_index"] = index
    context.user_data["habit_hour"] = datetime.datetime.now().hour

    if not context.job_queue.get_jobs_by_name(f"hour-{user.external_id}"):
        context.job_queue.run_once(callback=callback_hour, when=60 * 60, chat_id=update.effective_user.id,
                                   name=f"hour-{user.external_id}")
    if not context.job_queue.get_jobs_by_name(f"3hours-{user.external_id}"):
        context.job_queue.run_once(callback=callback_3hours, when=3 * 60 * 60, chat_id=update.effective_user.id,
                                   name=f"3hours-{user.external_id}")

    if is_com:
        previous_sub: Sub = await Sub.objects.aget(pk=habit_list[index - 1])
        previous_sub.score += 1
        context.user_data["score"] += (await previous_sub.aget_post()).score
        await previous_sub.asave()

    if index < len(habit_list):
        current_sub: Sub = await Sub.objects.aget(pk=habit_list[index])
        post = await current_sub.aget_post()

        reply_text = f"{index + 1}) {post.title}"

        extended = data.copy()
        extended["n"] = False
        extended["e"] = True

        skip_button = deepcopy(data)
        skip_button["hq"].append(skip_button["hq"][index])
        skip_button["hq"].pop(index)
        skip_button["c"] = False
        skip_button["e"] = False

        data["i"] += 1
        data["n"] = True
        data["e"] = False

        completed = data.copy()
        completed["c"] = True

        not_completed = data.copy()
        not_completed["c"] = False

        # TODO: change callback data when fixing timer
        if is_extended:
            keyboard = [[InlineKeyboardButton(text=f"Выполнил(а) ✅",
                                              callback_data=f"key={await write_state(completed)}")]]
        else:
            keyboard = [[InlineKeyboardButton(text=f"({post.lead_time} сек) Выполнил(а) ✅",
                                              callback_data=f"key={await write_state(completed)}")]]
        keyboard.append(
            [InlineKeyboardButton(text="Не выполнил(а)❌", callback_data=f"key={await write_state(not_completed)}")])

        if index < len(data.items()) - 2:
            keyboard.append(
                [InlineKeyboardButton(text="Вернуться потом ▶️",
                                      callback_data=f"key={await write_state(skip_button)}")])

        if post.is_bot_habit:
            post = await Post.objects.aget(pk=post.pk)
            random_stimulus = await Stimulus.objects.all().order_by('?').afirst()

            if is_extended:
                for button_data in button_data_list:
                    cb_data = json.dumps({"field": button_data[0], "post_pk": post.pk})
                    keyboard.append([InlineKeyboardButton(text=button_data[1], callback_data=cb_data)])
            else:
                keyboard.append(
                    [InlineKeyboardButton("💡 Подробности", callback_data=f"key={await write_state(extended)}")])

            reply_markup = InlineKeyboardMarkup(keyboard)

            if new_message:
                reply_text = f"{random_stimulus.text}\n{reply_text}"
                current_message = await bot.sendVideo(video=post.video_id, chat_id=update.effective_user.id,
                                                      caption=reply_text,
                                                      reply_markup=reply_markup)
            else:
                current_message = await query.edit_message_reply_markup(reply_markup=reply_markup)
        else:
            post = await UserPost.objects.aget(pk=post.pk)
            if current_sub.score < 1:
                reply_text = f"Всего 1 выполнение и ты сможешь {post.reward1}\n{reply_text}"
            elif current_sub.score < 30:
                reply_text = f"Всего {30 - current_sub.score} выполнений и ты сможешь {post.reward30}\n{reply_text}"
            reply_markup = InlineKeyboardMarkup(keyboard)
            current_message = await bot.sendMessage(chat_id=update.effective_user.id, text=reply_text,
                                                    reply_markup=reply_markup)

        # TODO: fix this func
        """if not is_extended:
            context.job_queue.run_once(callback=callback_timer, when=0,
                                       data={"post": post, "cm": current_message, "completed": completed,
                                             "keyboard": keyboard}, chat_id=update.effective_user.id,
                                       name=f"habit-{current_message.id}-cnt")"""
    else:
        await remove_job(f"hour-{user.external_id}", context)
        await remove_job(f"3hours-{user.external_id}", context)
        score = context.user_data["score"]
        user.score += score
        await user.asave()

        keyboard = []
        reward_text = str()
        index = 1
        for reward in await user.check_level_rewards():
            reward_text += f"{index}) {reward.name}\n"
            keyboard.append(
                [InlineKeyboardButton(text=reward.name, callback_data=f"level_reward={reward.pk}")])
            index += 1
        for reward in await user.update_tag_rewards():
            reward_text += f"{index}) {reward.name}\n"
            keyboard.append(
                [InlineKeyboardButton(text=reward.name, callback_data=f"tag_reward={reward.pk}")])
            index += 1
        for sub in await user.aget_subs():
            post = await sub.aget_post()
            if not post.is_bot_habit:
                logging.info(f"Checking for self rewards user: {user}, post: {post}")
                post = await UserPost.objects.aget(pk=post.pk)
                if sub.score == 1:
                    reward_text += f"{index}) {post.reward1}"
                    index += 1
                if sub.score == 30:
                    reward_text += f"{index}) {post.reward30}"
                    index += 1

        reply_markup = InlineKeyboardMarkup(keyboard)

        if len(reward_text):
            reward_text = "🏆 Положенные награды:\n" + reward_text

        full_score = 0
        async for sub in Sub.objects.filter(pk__in=habit_list):
            full_score += (await sub.aget_post()).score

        if score == 0:
            await bot.sendMessage(chat_id=update.effective_user.id, text=text["habits ended zero"])
        elif score == full_score:
            user.score += int(score * 0.2)
            await bot.sendMessage(chat_id=update.effective_user.id, text=text["habits ended full"] % (
                int(score * 1.2), await user.get_level(), await user.get_level_progress(), reward_text),
                                  reply_markup=reply_markup)
        else:
            await bot.sendMessage(chat_id=update.effective_user.id, text=text["habits ended particularly"] % (
                score, await user.get_level(), await user.get_level_progress(), reward_text), reply_markup=reply_markup)
        await user.asave()
        context.user_data["habit_query"] = False
        context.user_data["score"] = 0


async def prosrocheno(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Очередь привычек недоступна.")


async def commit_zag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Будьте честны с собой")


TITLE, AIM, LTIME, REWARD1, REWARD30, DAYTIME = range(6)


@requirements_required
@sign_up_required
async def create_habit_commit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    back_button = InlineKeyboardMarkup([[InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=MAIN_MENU)]])

    await query.edit_message_text(text="Чтобы создать свою привычку нажмите /create_habit", reply_markup=back_button)


@requirements_required
@sign_up_required
async def start_form_habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await bot.sendMessage(chat_id=update.effective_user.id,
                          text="Введите название привычки (например: Изучение английского)")
    return TITLE


async def set_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["create habit"] = dict()
    context.user_data["create habit"]["title"] = update.message.text
    await update.message.reply_text("Введите цель (например: Устроиться в мировую компанию)")
    return AIM


async def set_aim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["create habit"]["aim"] = update.message.text
    await update.message.reply_text("Введите время выполнения (в минутах)")
    return LTIME


async def set_ltime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if msg.isdigit():
        context.user_data["create habit"]["ltime"] = int(msg)
        await update.message.reply_text("Введите награду за 1 выполнение (например: Съесть любимый фрукт)")
        return REWARD1
    else:
        await update.message.reply_text("Введите число!")
        return LTIME


async def set_reward1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["create habit"]["reward1"] = update.message.text
    await update.message.reply_text("Введите награду за 30 выполнений (например: Купить то, о чём давно мечтал)")
    return REWARD30


async def set_reward30(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["create habit"]["reward30"] = update.message.text
    await update.message.reply_text("Введите время дня (Утро/День/Вечер)",
                                    reply_markup=ReplyKeyboardMarkup([["Утро", "День", "Вечер"]]))
    return DAYTIME


async def set_daytime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    d = {"Утро": "M", "День": "N", "Вечер": "E"}
    if msg.text in d.keys():
        context.user_data["create habit"]["daytime"] = d[msg.text]
        habit_data = context.user_data["create habit"]
        user_post = await UserPost.objects.acreate(
            title=habit_data["title"],
            lead_time=habit_data["ltime"] * 60,
            is_bot_habit=False,
            aim=habit_data["aim"],
            reward1=habit_data["reward1"],
            reward30=habit_data["reward30"]
        )
        user = await User.objects.aget(external_id=update.effective_user.id)
        sub = await Sub.objects.acreate(user=user, post=user_post)
        await Notification.objects.acreate(sub=sub, daytime=habit_data["daytime"])
        await msg.reply_text(f'Вы успешно создали привычку "{user_post.title}"', reply_markup=ReplyKeyboardRemove())

        await asyncio.sleep(2)
        await msg.reply_text(text=MENU_TEXT, reply_markup=await get_main_menu())

        return ConversationHandler.END
    else:
        await msg.reply_text("Упс! Ошибка. Попробуйте снова")
        return DAYTIME


def admin_required(func):
    @functools.wraps(func)
    async def decorator(update, context, *args, **kwargs):
        try:
            user = await User.objects.aget(external_id=update.effective_user.id)
            if user.is_admin:
                return await func(update, context, *args, **kwargs)
            return
        except:
            return

    return decorator


@admin_required
async def get_video_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(text=update.message.video.file_id)


@admin_required
async def get_photo_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(text=update.message.photo[-1].file_id)


# Achievements Static
MY_ACHIEVEMENTS, LEVEL_PRIZES = "MA", "LP"


async def user_achievements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_photos: list[PhotoSize] = (await update.effective_user.get_profile_photos())["photos"][0]
    user_photo = user_photos[-1]

    user = await User.objects.aget(pk=update.effective_user.id)

    reply_text = f"{user}\n\n"
    reply_text += f"🏆 Ваш уровень: {await user.get_level()} {await user.get_level_progress()}"
    keyboard = [
        [InlineKeyboardButton(text="🏆 Уровневые награды", callback_data=LEVEL_PRIZES)],
        [InlineKeyboardButton(text="🥇Мои Достижения", callback_data=MY_ACHIEVEMENTS)],
        [InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=MAIN_MENU)]
    ]

    await query.delete_message()
    await bot.sendPhoto(chat_id=update.effective_user.id, photo=user_photo, caption=reply_text,
                        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def user_tag_rewards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = await User.objects.aget(pk=update.effective_user.id)

    keyboard = []
    async for reward in TagReward.objects.filter(users__in=[user, ]):
        keyboard.append([InlineKeyboardButton(text=f"🌳 {reward.name}", callback_data=f"tag_reward={reward.pk}")])
    async for reward in TagReward.objects.exclude(users__in=[user, ]):
        keyboard.append([InlineKeyboardButton(text=f"🌱 {reward.name}", callback_data=f"tag_reward={reward.pk}")])
    keyboard.append([InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=ACHIEVEMENTS)])

    await query.delete_message()
    await bot.sendMessage(chat_id=update.effective_user.id, text="Достижения:",
                          reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def user_tag_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user: User = await User.objects.aget(external_id=update.effective_user.id)
    reward: TagReward = await TagReward.objects.aget(pk=int(query.data.split("=")[-1]))
    score, completed = await user.get_tag_reward_score(reward)

    reply_text = f"{reward.name}\n" \
                 f"{reward.text}\n"
    if completed:
        reply_text += "Прогресс: 100%\n" \
                      f"Награда: {reward.reward}\n"
    else:
        reply_text += f"Выполните упражнения {await reward.aget_tag()} {reward.score_required} раз чтобы получить награду\n" \
                      f"Прогресс: {round(round(score / reward.score_required, 2) * 100)}%\n"

    back_button = InlineKeyboardMarkup([[InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=MY_ACHIEVEMENTS)]])

    await query.delete_message()
    await bot.sendPhoto(chat_id=update.effective_user.id, photo=reward.photo_id, caption=reply_text,
                        reply_markup=back_button, parse_mode="HTML")


async def user_level_rewards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = await User.objects.aget(pk=update.effective_user.id)

    keyboard = []
    index = 0
    async for reward in LevelReward.objects.filter(users__in=[user, ]).order_by("level_required"):
        if index % 5 == 0:
            keyboard.append([])
        keyboard[-1].append(InlineKeyboardButton(text=f"🌳 {reward.name}", callback_data=f"level_reward={reward.pk}"))
        index += 1
    async for reward in LevelReward.objects.exclude(users__in=[user, ]).order_by("level_required"):
        if index % 5 == 0:
            keyboard.append([])
        keyboard[-1].append(
            InlineKeyboardButton(text=f"🌱 {reward.name}", callback_data=f"not_level_reward={reward.pk}"))
        index += 1

    keyboard.append([InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=ACHIEVEMENTS)])

    await query.delete_message()
    await bot.sendMessage(chat_id=update.effective_user.id, text="Уровневые награды:",
                          reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def user_level_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    reward: LevelReward = await LevelReward.objects.aget(pk=int(query.data.split("=")[-1]))

    reply_text = f"Награда за уровень {reward.level_required}\n" \
                 f"Награда: {reward.reward}"

    back_button = InlineKeyboardMarkup([[InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=LEVEL_PRIZES)]])

    await query.delete_message()
    await bot.sendPhoto(chat_id=update.effective_user.id, photo=reward.photo_id, caption=reply_text,
                        reply_markup=back_button, parse_mode="HTML")


async def user_level_reward_not_achieved(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    reward: LevelReward = await LevelReward.objects.aget(pk=int(query.data.split("=")[-1]))
    await query.answer(f"Достигните уровня {reward.level_required} чтобы получить эту награду", parse_mode="HTML")


CHANGE_SEX, CHANGE_AGE, CHANGE_UTC = range(10, 13)


async def user_profile_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.delete_message()

    user_photos: list[PhotoSize] = (await update.effective_user.get_profile_photos())["photos"][0]
    user_photo = user_photos[-1]

    user = await User.objects.aget(external_id=update.effective_user.id)

    keyboard = [
        [InlineKeyboardButton("📅 Настроить расписание", callback_data=SCHEDULE)],
        [InlineKeyboardButton("📝 Заполнить анкету заново", callback_data=SIGN_UP)],
        [InlineKeyboardButton("🌳 Служба заботы", url="https://t.me/BodnarSupport")],
        [InlineKeyboardButton(text=BACK_BUTTON_TEXT, callback_data=MAIN_MENU)],
    ]

    await bot.sendPhoto(chat_id=update.effective_user.id, photo=user_photo,
                        caption=f"Настройка вашего профиля:\nПол: {user.get_sex_display()}\nВозраст: {user.age}\nЧасовой пояс: {user.get_utc()}",
                        reply_markup=InlineKeyboardMarkup(keyboard))


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query

    if not query:
        return

    results = list()
    async for post in Post.objects.filter(title__contains=query):
        cb_data = json.dumps({"pc": post.pk, "e": True})
        results.append(InlineQueryResultCachedPhoto(
            id=str(uuid4()),
            title=post.title,
            description=post.description,
            photo_file_id=post.media_id,
            input_message_content=InputTextMessageContent(
                f't.me/{(await bot.get_me())["username"]}?post={post.pk}'
            ),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Посмотреть", callback_data=cb_data)]]),
        ))

    await update.inline_query.answer(results)


# run bot
def run_bot():
    registration_handler = ConversationHandler(
        entry_points=[CommandHandler("sign_up", sign_up), CallbackQueryHandler(sign_up, SIGN_UP)],
        states={
            SEX: [MessageHandler(filters.Regex("^(Мужской|Женский)$"), get_sex),
                  MessageHandler(filters.Regex("^(Пропустить)$"), skip_sex)],
            AGE: [MessageHandler(filters.Regex("^(Пропустить)$"), skip_age),
                  MessageHandler(filters.TEXT & (~ filters.COMMAND), get_age)],
            UTC: [MessageHandler(filters.Regex("^(Пропустить)$"), skip_utc),
                  MessageHandler(filters.TEXT, get_utc)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    create_habit_handler = ConversationHandler(
        entry_points=[CommandHandler("create_habit", start_form_habit)],
        states={
            TITLE: [MessageHandler(filters.TEXT & (~ filters.COMMAND), set_title)],
            AIM: [MessageHandler(filters.TEXT & (~ filters.COMMAND), set_aim)],
            LTIME: [MessageHandler(filters.TEXT & (~ filters.COMMAND), set_ltime)],
            REWARD1: [MessageHandler(filters.TEXT & (~ filters.COMMAND), set_reward1)],
            REWARD30: [MessageHandler(filters.TEXT & (~ filters.COMMAND), set_reward30)],
            DAYTIME: [MessageHandler(filters.TEXT & (~ filters.COMMAND), set_daytime)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(registration_handler)

    application.add_handler(CallbackQueryHandler(check_requirements, "check_requirements"))

    application.add_handler(CallbackQueryHandler(create_habit_commit, CREATE))
    application.add_handler(create_habit_handler)

    # Menu handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(share_ref_link, "share_ref_link"))
    application.add_handler(CommandHandler("menu", main_menu))
    application.add_handler(CallbackQueryHandler(main_menu_query, MAIN_MENU))

    # Zaglusski
    application.add_handler(CallbackQueryHandler(commit_zag, "com_zag"))
    application.add_handler(CallbackQueryHandler(prosrocheno, "prosrocheno"))

    # Profile Settings
    application.add_handler(CallbackQueryHandler(user_profile_settings, PROFILE_SETTINGS))
    application.add_handler(CallbackQueryHandler(sign_up, SIGN_UP))

    # Tag handlers
    application.add_handler(CallbackQueryHandler(tag_list, "tag_id=*"))
    application.add_handler(CallbackQueryHandler(subscribe_tag, "subscribe_tag=*"))
    application.add_handler(CallbackQueryHandler(unsubscribe_tag, "unsubscribe_tag=*"))
    application.add_handler(CallbackQueryHandler(user_tag_list, TAG_LIST))

    # Post handlers
    application.add_handler(CallbackQueryHandler(add_post_to_user, "add_post=*"))
    application.add_handler(InlineQueryHandler(inline_query))
    # application.add_handler(CallbackQueryHandler(post_prosloyka, "pros="))
    application.add_handler(CallbackQueryHandler(post_card, '{"pc'))
    application.add_handler(CallbackQueryHandler(user_post_list, POST_LIST))
    application.add_handler(CallbackQueryHandler(get_post_field, '{"field":'))
    application.add_handler(CommandHandler("habit", post_card))

    # Schedule handlers
    application.add_handler(CallbackQueryHandler(user_schedule, '{"daytime":'))
    application.add_handler(CallbackQueryHandler(zaglushka, "zaglushka"))
    application.add_handler(CallbackQueryHandler(habit_query, 'key='))

    # Sub handlers
    application.add_handler(CallbackQueryHandler(sub_settings, "sub_settings=*"))
    application.add_handler(CallbackQueryHandler(sub_settings_user_habit, "user_sub_settings="))
    application.add_handler(CallbackQueryHandler(set_default_schedule, "set_default_schedule=*"))
    application.add_handler(CallbackQueryHandler(delete_sub, "delete_sub=*")),
    application.add_handler(CallbackQueryHandler(completed_sub, "completed_sub=*"))
    application.add_handler(CallbackQueryHandler(not_completed_sub, "not_completed_sub=*"))
    application.add_handler(CallbackQueryHandler(today_subs, TODAY_HABITS))
    # application.add_handler(sub_settings_handler)

    # Achievements handlers
    application.add_handler(CallbackQueryHandler(user_achievements, ACHIEVEMENTS))
    application.add_handler(CallbackQueryHandler(user_tag_rewards, MY_ACHIEVEMENTS))
    application.add_handler(CallbackQueryHandler(user_level_rewards, LEVEL_PRIZES))
    application.add_handler(CallbackQueryHandler(user_tag_reward, f"tag_reward="))
    application.add_handler(CallbackQueryHandler(user_level_reward, "level_reward="))
    application.add_handler(CallbackQueryHandler(user_level_reward_not_achieved, "not_level_reward="))

    # Notification handlers
    application.add_handler(CallbackQueryHandler(create_notification, '{"cn":'))
    application.add_handler(CallbackQueryHandler(delete_notification, '{"dn":'))

    application.add_handler(CommandHandler("help", help))

    # Photo Video
    application.add_handler(MessageHandler(filters.VIDEO, get_video_id))
    application.add_handler(MessageHandler(filters.PHOTO, get_photo_id))

    # scheduler
    from .scheduler import CustomScheduler
    CustomScheduler.initialize(application)
    application.job_queue.run_repeating(callback=CustomScheduler._every_minute, interval=60)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


class Command(BaseCommand):
    help = "Telegram bot"

    def handle(self, *args, **options):
        run_bot()


if __name__ == "__main__":
    run_bot()
