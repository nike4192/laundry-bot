
import asyncio
import os
import pwd
from pathlib import Path
from crontab import CronTab

from telegram import BotCommand

import locales
from app import application


async def set_crontab():
    CWD = Path.cwd()
    PYTHON_PATH = os.environ.get('PYTHON_PATH') or \
                    'env/bin/python3.9'
    PYTHON_SCRIPT = 'cron-update.py'
    TAB_COMMAND = f'cd {CWD} && {PYTHON_PATH} {PYTHON_SCRIPT} >> logs/crontab.txt 2>&1'
    TAB_ID = 'CRON_TAB_ID'

    username = pwd.getpwuid(os.getuid()).pw_name
    cron = CronTab(user=username)

    tab_flag = False
    for job in cron.find_comment(TAB_ID):
        if job.command == TAB_COMMAND:
            tab_flag = True
        else:
            cron.remove(job)

    if not tab_flag:
        job = cron.new(command=TAB_COMMAND, comment=TAB_ID)
        job.minute.every(1)
        cron.write()


async def set_my_commands():
    await asyncio.gather(*[
        application.bot.set_my_commands(
            [
                BotCommand(command=cmd, description=desc)
                for cmd, desc in getattr(locales, language_code)['commands'].items()
            ],
            language_code=language_code
        )
        for language_code in locales.language_codes
    ])


async def main():
    await asyncio.gather(
        set_crontab(),
        set_my_commands())


if __name__ == '__main__':
    asyncio.run(main())
