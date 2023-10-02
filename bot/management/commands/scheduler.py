from aiofile import async_open
from telegram.ext import ContextTypes, Application

from .utils import write_state
from ...models import *


class CustomScheduler(object):
    application: Application = None
    bot: Bot = None
    weekdays = [i[0] for i in WeekDay.choices]

    @staticmethod
    def initialize(application: Application):
        CustomScheduler.application = application
        CustomScheduler.bot = application.bot

    @staticmethod
    async def _callback_delete_notification(context: ContextTypes.DEFAULT_TYPE):
        try:
            await CustomScheduler.bot.edit_message_reply_markup(chat_id=context.job.chat_id,
                                                                message_id=context.job.data["message_id"],
                                                                reply_markup=InlineKeyboardMarkup(
                                                                    [[InlineKeyboardButton(
                                                                        text="Не выполнено ❌",
                                                                        callback_data="prosrocheno")]]))
        except Exception as e:
            logging.warning(e)

    @staticmethod
    async def _send_notifications():
        from .bot import get_post_list_by_schedule
        async for user in User.objects.all():
            try:
                habits, daytime = await get_post_list_by_schedule(user, datetime.datetime.now().hour)
                reply_text = f"🍀 Доброго здоровья!\n\nТвои привычки на {daytime}:\n\n"
                if habits:
                    i = 1
                    habit_dict = list()
                    sum_time = 0
                    for h in habits:
                        post = await h.aget_post()
                        reply_text += f"{i}) {post.title}\n"
                        habit_dict.append(h.pk)
                        sum_time += post.lead_time
                        i += 1
                    hour, minute, second = sum_time // 3600, (sum_time // 60) % 60, sum_time % 60
                    if sum_time < 3600:
                        reply_text += f"\nОбщее вермя выполнения: {datetime.time(minute=minute, second=second).strftime('%M:%S')}\n"
                    else:
                        reply_text += f"\nОбщее вермя выполнения: {datetime.time(hour=hour, minute=minute, second=second).strftime('%H:%M:%S')}\n"
                    cb_data = {"hq": habit_dict, "i": 0, "c": False, "n": True, "e": False}
                    key = await write_state(cb_data)
                    logging.info(f"user {user} habbit list for {daytime}: {key}")
                    reply_markup = InlineKeyboardMarkup(
                        [[InlineKeyboardButton(text="Приступить", callback_data=f"key={key}")]])
                    message = await CustomScheduler.bot.sendMessage(chat_id=user.external_id, text=reply_text,
                                                                    reply_markup=reply_markup)
                    tomorrow = datetime.datetime.now() + datetime.timedelta(1)
                    CustomScheduler.application.job_queue.run_once(user_id=user.external_id,
                                                                   data={"message_id": message.id},
                                                                   callback=CustomScheduler._callback_delete_notification,
                                                                   chat_id=user.external_id, when=tomorrow,
                                                                   name=f"{message.id}-delete")
            except Exception as e:
                logging.warning(f"Error while sending notifications to {user}")
                logging.warning(e)

    # TODO: make state deletion
    @staticmethod
    async def _delete_states():
        current_date = datetime.datetime.now().strftime("%d%m%y")
        async with async_open(os.path.dirname(__file__) + "/states.json", "r+", encoding="utf-8") as f:
            data = await f.read()
            try:
                states: dict = json.loads(data)
                for item in states.items():
                    key, state = item
            except Exception as e:
                logging.warning(e)

    @staticmethod
    async def _handle_mailing():
        async for mail in Mailing.objects.all():
            differ = abs(datetime.datetime.now().timestamp() - mail.send_time.timestamp())
            if differ < 60:
                async for user in User.objects.all():
                    logging.info(f"Рассылка {mail.text[:30]} отправлена {user}")
                    chat_id = user.external_id
                    if mail.media_type == mail.MediaTypes.PHOTO:
                        await CustomScheduler.bot.sendPhoto(chat_id=chat_id, photo=mail.media_id, caption=mail.text)
                    elif mail.media_type == mail.MediaTypes.VIDEO:
                        await CustomScheduler.bot.sendVideo(chat_id=chat_id, video=mail.media_id, caption=mail.text)
                    elif mail.media_type == mail.MediaTypes.BLANK:
                        await CustomScheduler.bot.sendMessage(chat_id=chat_id, text=mail.text)

    @staticmethod
    async def _every_minute(context: ContextTypes.DEFAULT_TYPE):
        if datetime.datetime.now().minute == 0:
            await CustomScheduler._send_notifications()
        await CustomScheduler._handle_mailing()
