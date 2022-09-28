
import os
import logging
import asyncio

from dotenv import load_dotenv
load_dotenv()  # TZ Important

import time
time.tzset()  # Set timezone

from lib.handlers import user_handlers
from telegram.ext import ApplicationBuilder


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

application = ApplicationBuilder() \
    .token(os.environ['BOT_TOKEN']) \
    .build()


def main():
    application.add_handlers(user_handlers)
    application.run_polling()


if __name__ == '__main__':
    main()
