
import re
import asyncio
import logging
from datetime import datetime

import lib.constants as const
from lib.misc import append_locale_arg
from lib.forms.appointment import AppointmentForm
from lib.forms.reminder import ReminderForm
from lib.forms.summary import SummaryForm
from lib.models import session, User, Message, AppointmentData, SummaryData, UserRole, ReminderData, Appointment
from lib.middlewares import auth_user_middleware, message_form_middleware, user_permission_middleware
from lib.authorization import authorize

from sqlalchemy import select

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters

logger = logging.getLogger(__name__)


@auth_user_middleware
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('auth_user'):
        await update.message.reply_text(
            text="Для записи в прачечную введите комманду: /book"
        )
    else:
        await update.message.reply_text(
            parse_mode='Markdown',
            text="Прежде всего нужно авторизоваться\n\n"
                 "Для этого отправьте сообщение в формате:\n"
                 "```\n/auth <фамилия> <имя> <номер договора>```\n"
                 "Если у вас фамилия и имя совпадает с указанными в договоре, то просто:"
                 "```\n/auth <номер договора>\n```")


@auth_user_middleware
async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    auth_user = user_data['auth_user']
    if auth_user:
        data = AppointmentData()
        session.add(data)
        await session.commit()

        message_form = AppointmentForm(auth_user, data)
        await message_form.reply(update, context)

        user_data['message_form'] = message_form


@append_locale_arg('authorization')
async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE, locale: dict):
    user_data = context.user_data
    auth_user_args = tuple(context.args)
    from_user = update.effective_message.from_user

    if len(auth_user_args) == 1:
        first_name = from_user.first_name
        last_name = from_user.last_name
    elif len(auth_user_args) == 3:
        first_name = auth_user_args[1]
        last_name = auth_user_args[0]
    else:
        user_data['auth_flag'] = True
        return await update.effective_message.reply_text(
            parse_mode='Markdown',
            text=locale['action_text'].format(cmd_='')
        )

    order_number = auth_user_args[-1]
    auth_user, reason = await authorize(
        first_name, last_name, order_number,
        from_user.username, update.effective_message.chat_id)

    if reason != const.AUTH_NOT_FOUND:
        await context.bot.deleteMessage(
            chat_id=update.message.chat_id,
            message_id=update.message.id)

    text_postfix = locale['auth_postfix']
    locale_key = const.AUTH_REASON_LOCALE_MAP[reason]
    msg_text = locale[locale_key].format(text_postfix)

    await update.effective_message.reply_text(msg_text)

    if auth_user:
        user_data['auth_user'] = auth_user
        user_data['auth_flag'] = False


async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('auth_flag'):
        context.args = re.split(r'\s+', update.message.text)
        return await auth(update, context)


@auth_user_middleware
@message_form_middleware
async def callback_query_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_form = context.user_data['message_form']
    query = update.callback_query
    await query.answer()

    state, value = query.data.split(' ')
    message_form.data.state = int(state)
    await message_form.button_handler(update, context, value)
    await message_form.update_message(update, context)

    data = message_form.data
    if isinstance(data, AppointmentData):
        if data.state == len(message_form.actions) - 1:
            # Update appointment forms for other users
            stmt = select(AppointmentData, User).where(
                AppointmentData.id != data.id,
                AppointmentData.message_id == Message.id,
                Message.user_id == User.id)

            appointment_gather = [
                AppointmentForm(user, data).update_message(update, context)
                for data, user in (await session.execute(stmt)).unique()
            ]
            # Update summary forms for moderators
            stmt = select(SummaryData, User) \
                .where(
                    SummaryData.summary_date,
                    SummaryData.message_id == Message.id,
                    Message.user_id == User.id)

            summary_gather = [
                SummaryForm(user, data).update_message(update, context)
                for data, user in (await session.execute(stmt)).unique()
                if data.message is not None
            ]

            await asyncio.gather(*appointment_gather, *summary_gather)


@auth_user_middleware
async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    auth_user = user_data['auth_user']
    if auth_user:
        data = ReminderData()
        session.add(data)
        await session.commit()

        message_form = ReminderForm(auth_user, data)
        await message_form.reply(update, context)

        user_data['message_form'] = message_form


@auth_user_middleware
async def my(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth_user = context.user_data['auth_user']

    stmt = select(AppointmentData, User) \
        .where(
            AppointmentData.expired == False,
            AppointmentData.message_id == Message.id,
            Message.user_id == User.id == auth_user.id,
            AppointmentData.id == Appointment.data_id) \
        .order_by(
            AppointmentData.book_date,
            AppointmentData.book_time)

    active_datas = (await session.execute(stmt)).unique().fetchall()
    if active_datas:
        # Close old forms
        closed_forms = asyncio.gather(*[
            AppointmentForm(user, data).close(0, context.bot)
            for data, user in active_datas
        ])

        # Reply new forms concurrently
        for data, user in active_datas:
            await asyncio.create_task(
                AppointmentForm(user, data).reply(update, context))

        await closed_forms
    else:
        await update.effective_message.reply_text(
            text='На данный момент нет действующих записей'
        )


@auth_user_middleware
@user_permission_middleware(UserRole.moderator)
async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    auth_user = user_data['auth_user']
    now_dt = datetime.now()

    data = SummaryData(summary_date=now_dt.date(), state=1)
    session.add(data)
    await session.commit()

    summary_form = SummaryForm(auth_user, data)
    await summary_form.reply(update, context)
    user_data['message_form'] = summary_form


@auth_user_middleware
@user_permission_middleware(UserRole.moderator)
async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    auth_user = user_data['auth_user']

    data = SummaryData()
    session.add(data)
    await session.commit()

    summary_form = SummaryForm(auth_user, data)
    await summary_form.reply(update, context)

    user_data['message_form'] = summary_form


user_handlers = [
    CommandHandler('auth', auth),
    CommandHandler('start', start),
    CommandHandler('book', book),
    CommandHandler('remind', remind),
    CommandHandler('my', my),
    CommandHandler('today', today),  # Moderator command
    CommandHandler('summary', summary),  # Moderator command
    CallbackQueryHandler(callback_query_button),
    # https://docs.python-telegram-bot.org/en/v20.0a4/examples.echobot.html
    MessageHandler(filters.TEXT & ~filters.COMMAND, message)
]
