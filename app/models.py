from sqlalchemy import ForeignKey, Column, Integer, String, Float, DateTime, Text, Index
from app.database import Base
from datetime import datetime
from sqlalchemy.orm import relationship

class Charger(Base):
    __tablename__ = "chargers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    city = Column(String, index=True)
    latitude = Column(Float)
    longitude = Column(Float)
    usage_type = Column(String, index=True)
    connector_type = Column(String)
    status = Column(String, default="unknown", index=True)  # unknown, working, broken
    status_updated_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    reviews = relationship("Review", back_populates="charger", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="charger", cascade="all, delete-orphan")
    reports = relationship("ChargerReport", back_populates="charger", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="member")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    reviews = relationship("Review", back_populates="user")
    vehicles = relationship("Vehicle", back_populates="user", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="user", cascade="all, delete-orphan")
    trips = relationship("Trip", back_populates="user", cascade="all, delete-orphan")
    reports = relationship("ChargerReport", back_populates="user")

class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    helpful_count = Column(Integer, default=0)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    charger_id = Column(Integer, ForeignKey("chargers.id", ondelete="CASCADE"))
    
    # Relationships
    user = relationship("User", back_populates="reviews")
    charger = relationship("Charger", back_populates="reviews")
    
    __table_args__ = (
        Index('ix_reviews_charger_id', 'charger_id'),
        Index('ix_reviews_user_id', 'user_id'),
    )

class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    connector_type = Column(String, nullable=False)
    range_km = Column(Float, nullable=True)
    battery_capacity_kwh = Column(Float, nullable=True)
    
    # Relationship
    user = relationship("User", back_populates="vehicles")

class Favorite(Base):
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    charger_id = Column(Integer, ForeignKey("chargers.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="favorites")
    charger = relationship("Charger", back_populates="favorites")
    
    __table_args__ = (
        Index('ix_favorites_user_charger', 'user_id', 'charger_id', unique=True),
    )

class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    start_lat = Column(Float, nullable=False)
    start_lon = Column(Float, nullable=False)
    end_lat = Column(Float, nullable=False)
    end_lon = Column(Float, nullable=False)

    waypoints = Column(Text, default="[]")
    total_distance_km = Column(Float)
    estimated_duration_minutes = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    user = relationship("User", back_populates="trips")

class ChargerReport(Base):
    __tablename__ = "charger_reports"

    id = Column(Integer, primary_key=True, index=True)
    charger_id = Column(Integer, ForeignKey("chargers.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    issue_type = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String, default="open")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    charger = relationship("Charger", back_populates="reports")
    user = relationship("User", back_populates="reports")