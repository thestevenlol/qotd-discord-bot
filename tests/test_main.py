import os
import sys
import pathlib
import importlib
import pytest
import discord
import aiosqlite
from apscheduler.triggers.cron import CronTrigger

# Ensure project root is on the import path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

class DummyGuild:
    def get_role(self, rid):
        return None

class DummyChannel:
    def __init__(self, id=1):
        self.id = id
        self.guild = DummyGuild()
        self.sent = []

    async def send(self, content=None, embed=None):
        self.sent.append({'content': content, 'embed': embed})

@pytest.mark.asyncio
async def test_schedule_question_daily(monkeypatch):
    import main as main_mod
    main = importlib.reload(main_mod)
    captured = {}
    def fake_add_job(func, trigger, args, id, replace_existing):
        captured['func'] = func
        captured['trigger'] = trigger
        captured['args'] = args
        captured['id'] = id
        captured['replace_existing'] = replace_existing
    monkeypatch.setattr(main.scheduler, 'add_job', fake_add_job)

    cfg = {'channel_id': 42, 'time': '12:34', 'frequency': 'daily'}
    await main.schedule_question(cfg)

    assert captured['args'] == [42]
    assert captured['id'] == 'qotd_42'
    assert captured['replace_existing'] is True
    assert isinstance(captured['trigger'], CronTrigger)
    rep = str(captured['trigger'])
    assert "hour='12'" in rep and "minute='34'" in rep

@pytest.mark.asyncio
async def test_schedule_question_weekly(monkeypatch):
    import main as main_mod
    main = importlib.reload(main_mod)
    captured = {}
    def fake_add_job(func, trigger, args, id, replace_existing):
        captured['trigger'] = trigger
    monkeypatch.setattr(main.scheduler, 'add_job', fake_add_job)
    cfg = {'channel_id': 1, 'time': '08:00', 'frequency': 'weekly-2'}
    await main.schedule_question(cfg)
    rep = str(captured['trigger'])
    assert "day_of_week='2'" in rep
    assert "hour='8'" in rep

@pytest.mark.asyncio
async def test_send_question_to_channel_no_config(tmp_path, monkeypatch):
    os.environ['DB_PATH'] = str(tmp_path/'test.db')
    import main as main_mod
    main = importlib.reload(main_mod)
    await main.setup_database()

    channel = DummyChannel()
    await main.send_question_to_channel(channel)
    assert channel.sent == []

@pytest.mark.asyncio
async def test_send_question_to_channel(tmp_path, monkeypatch):
    os.environ['DB_PATH'] = str(tmp_path/'test.db')
    import main as main_mod
    main = importlib.reload(main_mod)
    await main.setup_database()

    channel = DummyChannel()
    async with aiosqlite.connect(os.environ['DB_PATH']) as conn:
        await conn.execute(
            "INSERT INTO question_packs (guild_id, name, description, created_by) VALUES (1, 'pack', 'desc', 1)"
        )
        await conn.execute(
            "INSERT INTO questions (pack_id, content, created_by) VALUES (1, 'What?', 1)"
        )
        await conn.execute(
            "INSERT INTO channel_config (channel_id, guild_id, time, frequency, ping_role_id, last_question_id) VALUES (?, 1, '00:00', 'daily', NULL, NULL)",
            (channel.id,)
        )
        await conn.execute(
            "INSERT INTO channel_packs (channel_id, pack_id) VALUES (?, 1)",
            (channel.id,)
        )
        await conn.commit()

    await main.send_question_to_channel(channel)
    assert len(channel.sent) == 1
    msg = channel.sent[0]
    assert msg['content'] is None
    assert isinstance(msg['embed'], discord.Embed)

    async with aiosqlite.connect(os.environ['DB_PATH']) as conn:
        async with conn.execute("SELECT last_question_id FROM channel_config WHERE channel_id = ?", (channel.id,)) as cur:
            row = await cur.fetchone()
            assert row[0] == 1
