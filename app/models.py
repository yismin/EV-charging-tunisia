from sqlalchemy import ForeignKey, Column, Integer, String, Float,  DateTime
from app.database import Base
from datetime import datetime
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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    connector_type = Column(String, nullable=False)
    range_km = Column(Float, nullable=True)


class Favorite(Base):
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    charger_id = Column(Integer, ForeignKey("chargers.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    start_lat = Column(Float, nullable=False)
    start_lon = Column(Float, nullable=False)
    end_lat = Column(Float, nullable=False)
    end_lon = Column(Float, nullable=False)

    waypoints = Column(String, default="[]")  # JSON string
    total_distance_km = Column(Float)
    estimated_duration_minutes = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)