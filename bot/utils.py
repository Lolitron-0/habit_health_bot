import os

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Bot
import os, ffmpeg


async def send_notification_post(user, post, tag):
    bot = Bot(token=os.environ["BOT_TOKEN"])
    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="Посмотреть привычку", callback_data=f"post_card={post.pk}")]])
    await bot.sendMessage(chat_id=user.external_id,
                          text=f"По вашей подписке {tag} появилась новая привычка!",
                          reply_markup=reply_markup)
