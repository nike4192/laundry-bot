
import asyncio
import subprocess
import argparse

from dotenv import load_dotenv
load_dotenv('.env.test')

from lib.models import init as db_init


parser = argparse.ArgumentParser()
parser.add_argument('--subprocess', '-s', nargs='?', default=4, type=int)

args = parser.parse_args()
consumers = []

async def main():
    global producer

    await db_init()
    producer = subprocess.Popen(['env/bin/python', 'rmq_producer.py'])
    for i in range(args.subprocess):
        consumer = subprocess.Popen(['env/bin/python', 'rmq_consumer.py', str(i)])
        consumers.append(consumer)

    producer.wait()
    for consumer in consumers:
        consumer.wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        for c in consumers:
            c.kill()
