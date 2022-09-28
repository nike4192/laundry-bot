
from sqlalchemy import select

from typing import Union
import lib.constants as const
from lib.models import User, async_session, session


async def authorize(first_name, last_name, order_number, username, chat_id) -> tuple[Union[User, None], int]:
    stmt = select(User).where(
        User.first_name == first_name,
        User.last_name == last_name,
        User.order_number == order_number)

    auth_user = (await session.scalars(stmt)).unique().one_or_none()
    if auth_user:
        if auth_user.chat_id:
            if auth_user.chat_id == chat_id:
                return auth_user, const.SELF_ALREADY_AUTHORIZED
            else:
                return None, const.OTHER_ALREADY_AUTHORIZED
        else:
            auth_user.username = username
            auth_user.chat_id = chat_id
            async_session.commit()
            return auth_user, const.AUTH_SUCCESSFUL
    else:
        return None, const.AUTH_NOT_FOUND
