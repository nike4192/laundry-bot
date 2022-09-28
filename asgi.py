
import threading
from dotenv import load_dotenv
from lib.handlers import user_handlers
from lib.models import engine, Base, async_session

load_dotenv()

import os
import asyncio
import logging

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from telegram import Update
from telegram.ext import Application

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

class AppWorker:
    def __init__(self, number, session, data_queue):
        threading.Thread.__init__(self)
        self.number = number
        self.data_queue = data_queue
        application = Application.builder() \
            .token(os.environ['BOT_TOKEN']).updater(None).build()
        application.add_handlers(user_handlers)
        application.bot_data['session'] = session
        self.application = application

    async def start(self):
        await self.application.initialize()
        await asyncio.create_task(self.application.start())
        logger.info('AppWorker %s started' % self.number)
        # print(self.application.bot)
        while True:
            data = await self.data_queue.get()
            try:
                await self.application.update_queue.put(
                    Update.de_json(data=data, bot=self.application.bot)
                )
                print('AppWorker %s handler' % self.number)
            finally:
                self.data_queue.task_done()

# def create_app():
#     application = Application.builder().token(os.environ['BOT_TOKEN']).updater(None).build()
#     application.update_queue = update_queue
#     application.add_handlers(user_handlers)
#     await application.initialize()
#     await application.start()

url = "https://vps.coor.xyz"
# admin_chat_id = 123456
port = 8000

async def main() -> None:
    """Set up the application and a custom webserver."""
    # print('MAIN', file=sys.stderr)

    # context_types = ContextTypes(context=CustomContext)
    # Here we set updater to None because we want our custom webhook server to handle the updates
    # and hence we don't need an Updater instance
    # application.add_handlers(user_handlers)
    # save the values in `bot_data` such that we may easily access them in the callbacks
    # application.bot_data["url"] = url
    # application.bot_data["admin_chat_id"] = admin_chat_id

    # register handlers
    # application.add_handler(CommandHandler("start", start))
    # application.add_handler(TypeHandler(type=WebhookUpdate, callback=webhook_update))

    # Pass webhook settings to telegram
    # await application.bot.set_webhook(url=f"{url}/laundry-bot/")

    # Set up webserver
    async def telegram(request: Request) -> Response:
        """Handle incoming Telegram updates by putting them into the `update_queue`"""
        data = await request.json()
        await data_queue.put(
            data
        )
        return Response()

    starlette_app = Starlette(
        routes=[
            Route("/", telegram, methods=["POST"]),
        ]
    )

    webserver = uvicorn.Server(
        config=uvicorn.Config(
            app=starlette_app,
            port=port,
            use_colors=True,
            host="127.0.0.1"
        )
    )

    data_queue = asyncio.Queue()
    workers = [
        AppWorker(x, async_session(), data_queue).start()
        for x in range(1, 4)
    ]
    # for x in range(8):
    #     worker = AppWorker(data_queue)
    #     # Setting daemon to True will let the main thread exit even though the workers are blocking
    #     worker.daemon = True
    #     worker.start()
    #     # await worker.start()
    #     # Put the tasks into the queue as a tuple

    # Run application and webserver together
    # async with application:
    # await application.initialize()
    #     await application.start()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await asyncio.gather(*workers, webserver.serve())

        await asyncio.gather(*[
            worker.application.stop()
            for worker in workers
        ])
        # await application.stop()


if __name__ == "__main__":
    asyncio.run(main())