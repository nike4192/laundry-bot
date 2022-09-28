
from sqlalchemy.orm import selectinload

from lib.forms.appointment import AppointmentForm
from lib.forms.reminder import ReminderForm
from lib.forms.summary import SummaryForm
from lib.misc import append_locale_arg
from lib.models import session, UserRole, User, AppointmentData, ReminderData, SummaryData
from sqlalchemy import select


def auth_user_middleware(func):
    @append_locale_arg()
    async def wrapper(*args, **kwargs):
        update, context, locale = args[:3]
        user_data = context.user_data
        if not user_data.get('auth_user'):
            stmt = select(User) \
                .where(
                    User.chat_id == update.effective_message.chat_id) \
                .options(
                    selectinload(User.appointments))
            auth_user = (await session.scalars(stmt)).unique().one_or_none()
            if auth_user:
                user_data['auth_user'] = auth_user
            else:
                action_text = locale['authorization']['action_text'].format(cmd_='/auth ')
                return await update.message.reply_text(
                    parse_mode='Markdown',
                    text='%s\n\n%s' % (
                        locale['middlewares']['auth_user'],
                        action_text)
                )
        return await func(*args[:-1], **kwargs)  # Remove append locale arg
    return wrapper


def message_form_middleware(func):
    async def wrapper(*args, **kwargs):
        update, context = args
        user_data = context.user_data
        auth_user = user_data['auth_user']
        msg_id = update.effective_message.id

        if auth_user and (
            not user_data.get('message_form') or  # Not message_form
            user_data['message_form'].message.id != msg_id):  # message_form not for current message
            for MessageForm in [AppointmentForm, ReminderForm, SummaryForm]:
                FormData = MessageForm.__data_class__
                stmt = select(FormData) \
                    .where(
                        FormData.message_id == msg_id)
                data = (await session.scalars(stmt)).unique().one_or_none()
                if data:
                    user_data['message_form'] = MessageForm(auth_user, data)
                    break
        return await func(*args, **kwargs)
    return wrapper


def user_permission_middleware(*user_roles: UserRole):
    def wrapped(func):
        @append_locale_arg('middlewares')
        async def wrapper(*args, **kwargs):
            update, context, locale = args[:3]
            auth_user = context.user_data['auth_user']
            if auth_user.role in user_roles:
                return await func(*args[:-1], **kwargs)  # Remove append locale arg
            else:
                await update.effective_message.reply_text(
                    locale['user_permission']
                )
        return wrapper
    return wrapped
