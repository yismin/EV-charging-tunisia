# main.py
from fastapi import FastAPI, Depends, Query
from sqlalchemy.orm import Session
from app.database import SessionLocal, Base, engine
from app.models import Charger

# Create tables 
Base.metadata.create_all(bind=engine)

app = FastAPI(title="TuniCharge API")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/chargers")
def get_chargers(db: Session = Depends(get_db)):
    return db.query(Charger).all()

@app.get("/chargers/search")
def search_chargers(
    city: str = Query(None, description="Filter by city"),
    usage_type: str = Query(None, description="Filter by usage type"),
    db: Session = Depends(get_db)
):
    query = db.query(Charger)
    if city:
        query = query.filter(Charger.city.ilike(f"%{city}%"))
    if usage_type:
        query = query.filter(Charger.usage_type.ilike(f"%{usage_type}%"))
    return query.all()
