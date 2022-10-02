import os
from datetime import datetime
from sqlalchemy import Column, ForeignKey, Date, Time, Integer, String, Boolean, Enum, create_engine, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, declared_attr, Session
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy import func

from lib.constants import UserRole

mysql_user = os.getenv('MYSQL_USER')
mysql_password = os.getenv('MYSQL_PASSWORD')
mysql_host = os.getenv('MYSQL_HOST')
mysql_db = os.getenv('MYSQL_DB')

engine = create_async_engine(f'mysql+asyncmy://{mysql_user}:{mysql_password}@{mysql_host}/{mysql_db}')
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    first_name = Column(String(60))
    last_name = Column(String(60))
    order_number = Column(String(30))
    username = Column(String(60))
    chat_id = Column(BIGINT(unsigned=True))
    role = Column(Enum(UserRole), default=UserRole.user)

    messages = relationship("Message", back_populates="user")
    appointments = relationship("Appointment", back_populates="user", lazy="joined")
    reminders = relationship("Reminder", back_populates="user")  # , lazy="dynamic")

    def __repr__(self):
        return f'User(id={self.id!r}, first_name={self.first_name!r}, last_name={self.last_name!r}, order_number={self.order_number!r})'


class BaseData(Base):
    __abstract__ = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state = kwargs['state'] if kwargs.get('state') else 0

    id = Column(Integer, primary_key=True)
    state = Column(Integer, default=0)

    @declared_attr
    def message_id(cls):
        return Column(Integer, ForeignKey('messages.id'))

    @declared_attr
    def message(self):
        return relationship("Message", uselist=False, lazy='joined')


class AppointmentData(BaseData):
    __tablename__ = 'appointment_data'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    book_date = Column(Date)
    book_time = Column(Time)
    reserved = Column(Boolean, default=False)

    appointments = relationship("Appointment", back_populates="data", lazy='joined')

    @hybrid_property
    def expired(self):
        now_dt = datetime.now()
        return \
            self.book_date and self.book_time and \
            now_dt > datetime.combine(self.book_date, self.book_time)

    @expired.expression
    def expired(cls):
        now_dt = datetime.now()
        return \
            cls.book_date and cls.book_time and \
            now_dt > func.timestamp(cls.book_date, cls.book_time)

    @property
    def washers(self):
        return {item.washer for item in self.appointments} \
            if self.message else None

    def allocate_to(self, other_data):  # Provide relationship models to other data
        for appointment in self.appointments:
            appointment.data_id = other_data.id

    def __repr__(self):
        return f'AppointemntData(id={self.id!r}, message_id={self.message_id})'


class ReminderData(BaseData):
    __tablename__ = 'reminder_data'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    reminders = relationship("Reminder", back_populates="data", lazy='joined')

    def __repr__(self):
        return f'ReminderData(id={self.id!r}, message_id={self.message_id}, reminders_count={len(self.reminders)})'

    def allocate_to(self, other_data):  # Provide relationship models to other data
        for reminder in self.reminders:
            reminder.data_id = other_data.id


class SummaryData(BaseData):
    __tablename__ = 'summary_data'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    summary_date = Column(Date)

    def allocate_to(self, other):
        pass


class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True, nullable=False)
    user = relationship("User", back_populates="messages", uselist=False)

    def __repr__(self):
        return f'Message(id={self.id!r}, user_id={self.user_id!r})'


class Reminder(Base):
    __tablename__ = 'reminders'

    id = Column(Integer, primary_key=True)
    seconds = Column(Integer, nullable=False)

    data_id = Column(Integer, ForeignKey("reminder_data.id"), nullable=False)
    data = relationship("ReminderData", back_populates="reminders")

    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    user = relationship("User", back_populates="reminders")


class Appointment(Base):
    __tablename__ = 'appointments'

    id = Column(Integer, primary_key=True)
    book_date = Column(Date)
    book_time = Column(Time)
    # rejected_at = Column(DateTime)

    @hybrid_property
    def book_datetime(self):
        dt = datetime.combine(self.book_date, self.book_time)
        return dt.strftime('%Y-%m-%d %H:%M')

    @book_datetime.expression
    def book_datetime(cls):
        return func.timestamp(cls.book_date, cls.book_time)

    @hybrid_property
    def passed(self):
        now_dt = datetime.now()
        return now_dt > datetime.combine(self.book_date, self.book_time)

    @passed.expression
    def passed(cls):
        now_dt = datetime.now()
        return now_dt > cls.book_datetime

    data_id = Column(Integer, ForeignKey("appointment_data.id"), nullable=False)
    data = relationship("AppointmentData", back_populates="appointments")

    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    user = relationship("User", back_populates="appointments")

    washer_id = Column(Integer, ForeignKey('washers.id'), nullable=False)
    washer = relationship('Washer', lazy='joined')

    __table_args__ = (
        UniqueConstraint('book_date', 'book_time', 'washer_id', 'user_id'),
    )

    def __repr__(self):
        return f'Appointment(id={self.id}, data_id={self.data_id}, user_id={self.user_id}, book_date={self.book_date}, book_time={self.book_time}, washer_id={self.washer_id})';


class Washer(Base):
    __tablename__ = 'washers'

    id = Column(Integer, primary_key=True)
    name = Column(String(30))
    available = Column(Boolean, default=True)

    def __repr__(self):
        return f'Washer(id={self.id}, name={self.name}, available={self.available})';

async def get_session():
    async with async_session() as session:
        return session

async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
