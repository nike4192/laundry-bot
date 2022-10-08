
import os
import sys
import json
import asyncio
import logging

from dotenv import load_dotenv
load_dotenv('.env.test')

import pika
from telegram import Update
from telegram.ext import ApplicationBuilder

from lib.models import async_session
from lib.handlers import user_handlers

number = sys.argv[1] if len(sys.argv) > 1 else '#'

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()
channel.queue_declare(queue='laundry.updates')

application = ApplicationBuilder() \
    .token(os.environ['BOT_TOKEN']) \
    .build()

def main():
    loop = asyncio.get_event_loop()
    asyncio.set_event_loop(loop)

    async def init():
        application.add_handlers(user_handlers)
        await application.initialize()
        await application.start()

    loop.run_until_complete(init())

    async def callback(ch, method, properties, body):
        data = json.loads(body)
        async with async_session() as session:
            application.bot_data['session'] = session
            await application.process_update(
                Update.de_json(data, application.bot)
            )
        print(" [x] %s Received %s" % (number, data['update_id']))

    def receive(ch, method, properties, body):
        loop.run_until_complete(callback(ch, method, properties, body))

    channel.basic_consume(queue='laundry.updates',
                          auto_ack=True,
                          on_message_callback=receive)

    print(' [*] Waiting for messages. To exit press CTRL+C')
    channel.start_consuming()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(application.stop())
            loop.run_until_complete(application.shutdown())
            sys.exit(0)
        except SystemExit:
            os._exit(0)
