
import os
import re
import html
import json
import asyncio
import logging
import traceback
from datetime import datetime

import lib.constants as const
from lib.misc import append_locale_arg
from lib.forms.appointment import AppointmentForm
from lib.forms.reminder import ReminderForm
from lib.forms.summary import SummaryForm
from lib.models import session, User, Message, AppointmentData, SummaryData, UserRole
from lib.middlewares import auth_user_middleware, message_form_middleware, user_permission_middleware
from lib.authorization import authorize

from sqlalchemy import select

from telegram import Update
from telegram.constants import ParseMode
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
        message_form = AppointmentForm(auth_user)
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
    auth_user, reason = authorize(
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
    message_form.button_handler(update, context, value)
    await message_form.update_message(update, context)

    data = message_form.data
    if isinstance(data, AppointmentData):
        if data.state == len(message_form.actions) - 1:
            # Update appointment forms for other users
            stmt = select(AppointmentData).where(
                AppointmentData.id != data.id)
            await asyncio.gather(*[
                AppointmentForm(data.message.user, data).update_message(update, context)
                for data in session.scalars(stmt).all()
                if data.message_id is not None
            ])
            # Update summary forms for moderators
            summary_datas = session.query(SummaryData) \
                .where(
                    SummaryData.summary_date is not None,
                    SummaryData.message_id is not None) \
                .all()
            await asyncio.gather(*[
                SummaryForm(data.message.user, data).update_message(update, context)
                for data in summary_datas
                if data.message_id is not None
            ])


@auth_user_middleware
async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    auth_user = user_data['auth_user']
    if auth_user:
        message_form = ReminderForm(auth_user)
        await message_form.reply(update, context)

        user_data['message_form'] = message_form


@auth_user_middleware
async def my(update: Update, context: ContextTypes.DEFAULT_TYPE):
    auth_user = context.user_data['auth_user']

    stmt = select(Message, AppointmentData) \
        .filter(
            Message.id == AppointmentData.message_id,
            Message.user_id == auth_user.id) \
        .order_by(
            AppointmentData.book_date,
            AppointmentData.book_time)

    active_datas = [data
        for message, data in session.execute(stmt).fetchall()
        if not data.expired and bool(data.appointments)
    ]

    if active_datas:
        # Close old forms
        await asyncio.gather(*[
            AppointmentForm(data.message.user, data).close(0, context.bot)
            for data in active_datas
        ])
        # Reply new forms concurrently
        for data in active_datas:
            await AppointmentForm(data.message.user, data).reply(update, context)
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

    print('today')
    data = SummaryData(summary_date=now_dt.date(), state=1)
    session.add(data)
    session.commit()

    summary_form = SummaryForm(auth_user, data)
    await summary_form.reply(update, context)
    user_data['message_form'] = summary_form


@auth_user_middleware
@user_permission_middleware(UserRole.moderator)
async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    auth_user = user_data['auth_user']

    summary_form = SummaryForm(auth_user)
    await summary_form.reply(update, context)
    user_data['message_form'] = summary_form


# Reference: https://docs.python-telegram-bot.org/en/v20.0a4/examples.errorhandlerbot.html
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    stmt = select(User).where(User.username == os.environ['DEVELOPER_USERNAME'])
    user = session.scalars(stmt).one_or_none()
    if user:
        # Finally, send the message
        await context.bot.send_message(
            chat_id=user.chat_id,
            text=message,
            parse_mode=ParseMode.HTML
        )


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
