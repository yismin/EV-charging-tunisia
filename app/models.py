from sqlalchemy import Column, Integer, String, Float
from app.database import Base

class Charger(Base):
    __tablename__ = "chargers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    city = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    usage_type = Column(String)