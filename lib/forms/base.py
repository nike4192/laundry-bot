
import asyncio
from abc import abstractmethod
from typing import Union

import lib.constants as const
from lib.models import User, BaseData, Message
from sqlalchemy.ext.asyncio import AsyncSession

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes


class BaseMessage:

    parse_mode = None

    @abstractmethod
    def text(self, session: AsyncSession, data: BaseData):
        pass


class BaseAction:
    def __init__(self, item_text: str, action_text: str):
        self.item_text = item_text
        self.action_text = action_text

    async def reply_markup(self, session: AsyncSession, user: User, data: BaseData, state: int):
        pass

    def item_stringify(self, data: BaseData):
        pass

    async def button_handler(self, session: AsyncSession, user: User, data: BaseData, value: str) -> tuple[bool, str]:
        pass

    @staticmethod
    async def is_available_slot(session: AsyncSession, user: User, data: BaseData, value: str):
        pass


class BaseForm:
    actions = []

    __data_class__ = None

    closed_text = None
    finished_text = None

    def __init__(self, session: AsyncSession, user: User, data: BaseData = None):
        self.session = session
        self.user = user
        self.data = data

        self.closed = False
        self.error_text = None

    @property
    def message(self):
        return self.data.message

    @message.setter
    def message(self, value):
        self.data.message = value

    @abstractmethod
    async def find_exists_datas(self, session: AsyncSession, data: BaseData):
        pass

    def allocate_data_if_necessary(func):
        async def wrapper(self, *args, **kwargs) -> None:
            context = args[1]
            session = context.bot_data['session']
            datas = await self.find_exists_datas(session, self.data)
            if datas:
                for data in datas:
                    data.allocate_to(self.data)  # 1. Provide to self.data
                await session.commit()
                await session.refresh(self.data)

                result = await func(self, *args, **kwargs)

                await asyncio.gather(*[  # 2. Refresh old datas before close forms
                    session.refresh(data)
                    for data in datas
                ])

                closed_forms = [
                    # Derived class
                    self.__class__(session, self.user, data) \
                        .close(const.MESSAGE_IS_NOT_RELEVANT, context.bot)
                    for data in datas
                    if data != self.data
                ]

                removed_datas = [
                    session.delete(data)  # 3. Remove old datas
                    for data in datas
                    if data != self.data
                ]

                await asyncio.gather(*closed_forms, *removed_datas)
                await session.commit()

                return result
            else:
                return await func(self, *args, **kwargs)
        return wrapper

    @property
    def finished(self) -> bool:
        return False

    @property
    def title_text(self) -> str:
        if self.error_text:
            return '🚫 ' + self.error_text
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
            text=await self.text(),
            reply_markup=await self.reply_markup()
        )

    def fill_kwargs(func):
        async def wrapper(self, *args, **kwargs):
            if issubclass(self.active_action.__class__, BaseMessage):
                kwargs['parse_mode'] = self.active_action.parse_mode
            return await func(self, *args, **kwargs)
        return wrapper

    @fill_kwargs
    async def close(self, reason: int, bot, **kwargs) -> None:
        if reason == const.MESSAGE_IS_NOT_RELEVANT:
            self.closed = True
        try:
            await bot.edit_message_text(
                chat_id=self.user.chat_id,
                message_id=self.message.id,
                text=await self.text(),
                parse_mode=kwargs.get('parse_mode') or 'Markdown')
        except TelegramError as e:  # Message is not modified ...
            pass

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, value: str):
        session = context.bot_data['session']
        result, error_text = await self.active_action \
            .button_handler(session, self.user, self.data, value)
        print('button_handler', self.data.state, value, self.data)
        if result:
            if self.data.state < len(self.actions) - 1:
                self.data.state += 1
                await session.commit()
        elif error_text:
            self.error_text = error_text
            context.job_queue.run_once(
                self.reset_error,
                const.error_visible_duration,
                data=(update, context))
        return result

    @fill_kwargs
    @allocate_data_if_necessary
    async def reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        session = context.bot_data['session']
        await session.refresh(self.data)
        msg = await update.effective_message.reply_text(
            parse_mode=kwargs.get('parse_mode') or 'Markdown',
            text=await self.text(),
            reply_markup=await self.reply_markup())

        self.message = Message(id=msg.id, user_id=self.user.id)
        session.add(self.message)
        await session.commit()

    async def text(self):
        if self.closed:
            return '⌛'
        elif issubclass(self.active_action.__class__, BaseMessage):
            return await self.active_action.text(self.session, self.data)
        else:
            return \
                f'{self.title_text}\n\n' + \
                '\n'.join([
                    f'{action.item_text}: ' + \
                        (f'*{action.item_stringify(self.data)}*' if i < self.data.state or self.finished else "...")
                    for i, action in enumerate(self.actions)
                ])

    async def reply_markup(self):
        if not self.closed and issubclass(self.active_action.__class__, BaseAction):
            return await self.active_action.reply_markup(self.session, self.user, self.data, self.data.state)
        else:
            return None

    @fill_kwargs
    @allocate_data_if_necessary  # Update arg is necessary for allocate_data_if_necessary
    async def update_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs) -> None:
        try:
            session = context.bot_data['session']
            await session.refresh(self.data)
            return await context.bot.edit_message_text(
                chat_id=self.user.chat_id,
                message_id=self.message.id,
                text=await self.text(),
                parse_mode=kwargs.get('parse_mode') or 'Markdown',
                reply_markup=await self.reply_markup())
        except TelegramError as e:
            pass
