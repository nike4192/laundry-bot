
import os
import sys
import json
import asyncio

from dotenv import load_dotenv
load_dotenv('.env.test')

import pika
from telegram.ext import ApplicationBuilder

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()
channel.queue_declare(queue='laundry.expired_messages')

application = ApplicationBuilder() \
    .token(os.environ['BOT_TOKEN']) \
    .build()

def main():
    loop = asyncio.get_event_loop()
    asyncio.set_event_loop(loop)

    async def init():
        await application.initialize()
        await application.start()

    loop.run_until_complete(init())

    async def callback(ch, method, properties, body):
        data = json.loads(body)
        await application.bot.edit_message_text(
            chat_id=data['chat_id'],
            message_id=data['message_id'],
            text='⌛')
        print(" [x] Received info about expired message")

    def receive(ch, method, properties, body):
        loop.run_until_complete(callback(ch, method, properties, body))

    channel.basic_consume(queue='laundry.expired_messages',
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
