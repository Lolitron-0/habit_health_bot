import os
import json
import datetime
from aiofile import async_open
from uuid import uuid4

from telegram.error import BadRequest


async def write_state(state: dict):
    async with async_open(os.path.dirname(__file__) + "/states.json", "r+", encoding="utf-8") as f:
        data = await f.read()
        try:
            states = json.loads(data)
        except Exception as e:
            states = dict()
    async with async_open(os.path.dirname(__file__) + "/states.json", "w", encoding="utf-8") as f:
        key = str(uuid4())
        state["dt"] = datetime.datetime.now().strftime("%d/%m/%y")
        states[key] = state
        await f.write(json.dumps(states))
    return key


async def delete_state(state_id: str):
    async with async_open(os.path.dirname(__file__) + "/states.json", "r+", encoding="utf-8") as f:
        data = await f.read()
        try:
            states = json.loads(data)
        except Exception as e:
            states = dict()
    async with async_open(os.path.dirname(__file__) + "/states.json", "w", encoding="utf-8") as f:
        states.pop(str(state_id))
        await f.write(json.dumps(states))


async def is_user_subscribed(user_id, channel_username, bot):
    try:
        member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        return member.status in ['member', 'creator', 'administrator']
    except BadRequest:
        return False


async def check_requirements_by_user(user, bot):
    if await is_user_subscribed(user.external_id, "@BodnarVitaliy", bot):
        user.is_subscribed = True
    else:
        user.is_subscribed = False
    await user.asave()
    cnt = 0
    async for ref_user in user.refs.all():
        if await is_user_subscribed(ref_user.external_id, "@BodnarVitaliy", bot):
            cnt += 1
    return user.is_subscribed, cnt
