
from dotenv import load_dotenv
load_dotenv()  # TZ Important

import time
time.tzset()

from lib.handlers import error_handler, user_handlers

import os
import logging
from telegram.ext import ApplicationBuilder


BOT_TOKEN = os.environ['BOT_TOKEN']

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

application = ApplicationBuilder().token(BOT_TOKEN).build()

if __name__ == '__main__':
    application.add_handlers(user_handlers)
    # application.add_error_handler(error_handler)
    application.run_polling()
