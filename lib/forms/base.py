
import asyncio
import functools
from abc import abstractmethod
from typing import Union

import lib.constants as const
from lib.models import session, User, BaseData, Message

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes


class BaseMessage:

    parse_mode = None

    @abstractmethod
    def text(self, data: BaseData):
        pass


class BaseAction:
    def __init__(self, item_text: str, action_text: str):
        self.item_text = item_text
        self.action_text = action_text

    def reply_markup(self, user: User, data: BaseData, state: int):
        pass

    def item_stringify(self, data: BaseData):
        pass

    def button_handler(self, user: User, data: BaseData, value: str) -> tuple[bool, str]:
        pass

    @staticmethod
    def is_available_slot(user: User, data: BaseData, value: str):
        pass


class BaseForm:
    actions = []

    finished_text = None
    passed_text = None
    closed_text = None

    def __init__(self, user: User, data: BaseData):
        self.user = user
        self.data = data
        self.message = data.message if data.message else None

        self.passed = False
        self.closed = False
        self.error_text = None

    @abstractmethod
    def find_exists_datas(self, data: BaseData):
        pass

    def allocate_data_if_necessary(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs) -> None:
            context = args[1]
            datas = self.find_exists_datas(self.data)
            if datas:
                for data in datas:
                    data.allocate_to(self.data)  # 1. Provide to self.data
                session.commit()
                await func(self, *args, **kwargs)
                await asyncio.gather(*[
                    # Derived class
                    self.__class__(self.user, data).close(0, context.bot)
                    for data in datas
                ])
                for data in datas:
                    session.delete(data)  # 2. Remove other datas
                session.commit()
            else:
                await func(self, *args, **kwargs)
        return wrapper

    @property
    def finished(self) -> bool:
        return False

    @property
    def title_text(self) -> str:
        if self.error_text:
            return '🚫 ' + self.error_text
        elif self.passed:
            return '📅 ' + self.passed_text
        elif self.closed:
            return '⌛ ' + self.closed_text
        elif self.finished:
            return '✅ ' + self.finished_text
        else:
            return (f'%s/%s ' % (self.data.state + 1, len(self.actions))
                    if len(self.actions) > 1 else '') + \
                    self.active_action.action_text

    @property
    def active_action(self) -> Union[BaseMessage, BaseAction]:
        return self.actions[self.data.state]

    async def reset_error(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.error_text = None
        update, context = context.job.data
        await update.effective_message.edit_text(
            parse_mode='Markdown',
            text=self.text(),
            reply_markup=self.reply_markup()
        )

    def fill_kwargs(func):
        async def wrapper(self, *args, **kwargs):
            if issubclass(self.active_action.__class__, BaseMessage):
                kwargs['parse_mode'] = self.active_action.parse_mode
            await func(self, *args, **kwargs)
        return wrapper

    @fill_kwargs
    async def close(self, reason: int, bot, **kwargs) -> None:
        if reason == 0:
            self.closed = True
        elif reason == 1:
            self.passed = True
        try:
            await bot.edit_message_text(
                chat_id=self.user.chat_id,
                message_id=self.message.id,
                text=self.text(),
                parse_mode=kwargs.get('parse_mode') or 'Markdown')
        except TelegramError as e:  # Message is not modified ...
            pass

    def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, value: str):
        result, error_text = self.active_action \
            .button_handler(self.user, self.data, value)
        print('button_handler', self.data.state, value, self.data)
        if result:
            if self.data.state < len(self.actions) - 1:
                self.data.state += 1
                session.commit()
        elif error_text:
            self.error_text = error_text
            context.job_queue.run_once(
                self.reset_error,
                const.error_visible_duration,
                data=(update, context))
        return result

    @fill_kwargs
    @allocate_data_if_necessary
    async def reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs) -> None:
        msg = await update.effective_message.reply_text(
            parse_mode=kwargs.get('parse_mode') or 'Markdown',
            text=self.text(),
            reply_markup=self.reply_markup())

        self.message = Message(id=msg.id, user=self.user)
        self.data.message = self.message
        session.add(self.message)
        session.commit()

    def text(self):
        return \
            f'{self.title_text}\n\n' + \
            '\n'.join([
                f'{action.item_text}: ' + \
                    (f'*{action.item_stringify(self.data)}*' if i < self.data.state or self.finished else "...")
                for i, action in enumerate(self.actions)
            ])

    def reply_markup(self):
        if not self.closed and issubclass(self.active_action.__class__, BaseAction):
            return self.active_action.reply_markup(self.user, self.data, self.data.state)
        else:
            return None

    @fill_kwargs
    @allocate_data_if_necessary  # Update arg is necessary for allocate_data_if_necessary
    async def update_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs) -> None:
        try:
            return await context.bot.edit_message_text(
                chat_id=self.user.chat_id,
                message_id=self.message.id,
                text=self.text(),
                parse_mode=kwargs.get('parse_mode') or 'Markdown',
                reply_markup=self.reply_markup())
        except TelegramError as e:
            pass
