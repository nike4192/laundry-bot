
import os
import logging
import asyncio

from dotenv import load_dotenv
load_dotenv()  # TZ Important

import time
time.tzset()  # Set timezone

from lib.models import get_session, init as db_init
from lib.handlers import user_handlers
from telegram.ext import ApplicationBuilder


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

application = ApplicationBuilder() \
    .token(os.environ['BOT_TOKEN']) \
    .build()

def main(session):
    application.bot_data['session'] = session
    application.add_handlers(user_handlers)
    application.run_polling()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        session = loop.run_until_complete(get_session())
        loop.run_until_complete(db_init())
        main(session)
    finally:
        loop.close()
