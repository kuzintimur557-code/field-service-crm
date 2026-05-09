from sqlalchemy import Column, Integer, String, Text, ForeignKey
from app.database import Base

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String)
    phone = Column(String)
    address = Column(String)
    description = Column(Text)

    status = Column(String, default="new")
    assigned_to = Column(String)
    scheduled_date = Column(String)

class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    author = Column(String)
    text = Column(Text)
