# Copyright (C) 2026 meta-magic_mount-rs developers
# SPDX-License-Identifier: GPL-v3

import telegram

from . import logger, settings


async def post(msg: str, parse_mode: str):
    logger.info("Posting message to Telegram")
    async with telegram.Bot(settings.bot_token) as bot:
        await bot.send_message(settings.chat_id, text=msg, parse_mode=parse_mode)
    logger.info("Successfully posted to Telegram")
