import os
import json
import datetime
from aiofile import async_open
from uuid import uuid4


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
