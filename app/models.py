from sqlalchemy import ForeignKey, Column, Integer, String, Float
from app.database import Base
from sqlalchemy.orm import relationship

class Charger(Base):
    __tablename__ = "chargers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    city = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    usage_type = Column(String)
    connector_type = Column(String)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="member")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    rating = Column(Integer, nullable=False)
    comment = Column(String, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"))
    charger_id = Column(Integer, ForeignKey("chargers.id"))

class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    connector_type = Column(String, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
