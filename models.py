from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, PickleType, inspect
from sqlalchemy.orm import relationship
from database import Base, engine
from sqlalchemy.ext.mutable import MutableList
from datetime import datetime
from logger import logger

class Group(Base):
    __tablename__ = "groups"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=True)
    
    topics = relationship("Topic", back_populates="group", cascade="all, delete")
    tasks = relationship("Task", back_populates="group")

class Topic(Base):
    __tablename__ = "topics"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String(255), nullable=False)
    link = Column(String(255), nullable=True)
    name = Column(String(255), nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    
    group = relationship("Group", back_populates="topics")
    tasks = relationship("Task", back_populates="topic")

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String(255), nullable=True)
    username = Column(String(255), nullable=False)
    is_admin = Column(Boolean, nullable=True, default=False)

    tasks = relationship("UserTask", back_populates="user")
    created_tasks = relationship("Task", back_populates="admin_user")

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=True)
    admin_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(DateTime, nullable=True, default=datetime.now)
    end_date = Column(DateTime, nullable=True)
    status = Column(String(50), default="pending", nullable=False)
    
    group = relationship("Group", back_populates="tasks")
    topic = relationship("Topic", back_populates="tasks")
    admin_user = relationship("User", back_populates="created_tasks")
    assigned_users = relationship("UserTask", back_populates="task")
    
    attachments = relationship("TaskAttachment", back_populates="task", cascade="all, delete")

class UserTask(Base):
    __tablename__ = "users_tasks"
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    
    user = relationship("User", back_populates="tasks")
    task = relationship("Task", back_populates="assigned_users")


class TaskAttachment(Base):
    __tablename__ = "task_attachments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    
    attachment_ids = Column(MutableList.as_mutable(PickleType), default=[]) 

    # Relationship back to the task
    task = relationship("Task", back_populates="attachments")


def init_db():
    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        if not existing_tables:
            logger.info("No existing tables found. Creating tables ...")
            Base.metadata.create_all(bind=engine)
            logger.info("Tables created successfully.")
        else:
            logger.info("Tables already exist. Skipping creation.")
    except Exception:
        logger.exception("Failed to create the tables")

if __name__ == "__main__":
    init_db()
