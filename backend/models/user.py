from sqlalchemy import Column,Integer,String
from backend.database import Base

class User(Base):
    __tablename__="users"

    id=Column(Integer,primary_key=True,index=True)
    phone = Column(String(13), unique=True, nullable=False)
    name = Column(String(100), nullable=False)