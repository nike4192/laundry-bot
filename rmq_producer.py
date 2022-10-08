
import asyncio
import json

import pika

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route


port = 8001

async def main():
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()

    channel.queue_declare(queue='laundry.updates')

    async def telegram(request: Request) -> Response:
        global user_counter
        """Handle incoming Telegram updates by putting them into the `update_queue`"""
        body = await request.body()
        data = json.loads(body)
        # user_id = get_user_id_from_update(data)
        # if user_id not in user_workers:
        #     user_counter += 1
        #     worker = AppWorker(user_counter, None, data_queue)
        #     worker.daemon = True
        #     await asyncio.create_task(worker.start())
        channel.basic_publish(exchange='',
                              routing_key='laundry.updates',
                              body=body)
        print(" [x] Sent %s" % data['update_id'])
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

    await webserver.serve()
    connection.close()

if __name__ == '__main__':
    asyncio.run(main())
