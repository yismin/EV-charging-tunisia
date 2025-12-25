# main.py
from fastapi import FastAPI, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal, Base, engine
from app.models import Charger
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
OPENROUTESERVICE_API_KEY = os.getenv("OPENROUTESERVICE_API_KEY")

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


def calculate_distance_via_api(start_lat: float, start_lon: float, 
                                end_lat: float, end_lon: float) -> dict:
    """
    Calculate driving distance between two points using OpenRouteService API.
    
    Args:
        start_lat: User's latitude
        start_lon: User's longitude
        end_lat: Charger's latitude
        end_lon: Charger's longitude
    
    Returns:
        dict with 'distance_km' and 'duration_minutes'
    """
    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    
    headers = {
        "Authorization": OPENROUTESERVICE_API_KEY
    }
    
    params = {
        "start": f"{start_lon},{start_lat}",  # Note: ORS uses lon,lat order
        "end": f"{end_lon},{end_lat}"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Extract distance and duration from response
        summary = data["features"][0]["properties"]["summary"]
        distance_meters = summary["distance"]
        duration_seconds = summary["duration"]
        
        return {
            "distance_km": round(distance_meters / 1000, 2),  # Convert to km
            "duration_minutes": round(duration_seconds / 60, 1)  # Convert to minutes
        }
    except requests.exceptions.RequestException as e:
        # If API call fails, return None so we can handle it gracefully
        print(f"Error calling OpenRouteService: {e}")
        return None


@app.get("/chargers")
def get_chargers(db: Session = Depends(get_db)):
    """Get all chargers without distance calculation."""
    return db.query(Charger).all()


@app.get("/chargers/search")
def search_chargers(
    city: str = Query(None, description="Filter by city"),
    usage_type: str = Query(None, description="Filter by usage type"),
    db: Session = Depends(get_db)
):
    """Search chargers by city or usage type."""
    query = db.query(Charger)
    if city:
        query = query.filter(Charger.city.ilike(f"%{city}%"))
    if usage_type:
        query = query.filter(Charger.usage_type.ilike(f"%{usage_type}%"))
    return query.all()


@app.get("/chargers/nearby")
def get_nearby_chargers(
    lat: float = Query(..., description="User's current latitude"),
    lon: float = Query(..., description="User's current longitude"),
    limit: int = Query(10, description="Number of nearest chargers to return", ge=1, le=27),
    db: Session = Depends(get_db)
):
    """
    Find nearest chargers based on real driving distance.
    
    This endpoint:
    1. Gets all chargers from database
    2. Calculates driving distance from user's location to each charger
    3. Sorts by distance
    4. Returns the nearest ones
    """
    # Validate coordinates
    if not (-90 <= lat <= 90):
        raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90")
    if not (-180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180")
    
    # Get all chargers from database
    chargers = db.query(Charger).all()
    
    if not chargers:
        raise HTTPException(status_code=404, detail="No chargers found in database")
    
    # Calculate distance for each charger
    chargers_with_distance = []
    
    for charger in chargers:
        # Call OpenRouteService API to get real driving distance
        distance_info = calculate_distance_via_api(
            start_lat=lat,
            start_lon=lon,
            end_lat=charger.latitude,
            end_lon=charger.longitude
        )
        
        if distance_info:  # Only include if API call succeeded
            chargers_with_distance.append({
                "id": charger.id,
                "name": charger.name,
                "city": charger.city,
                "latitude": charger.latitude,
                "longitude": charger.longitude,
                "usage_type": charger.usage_type,
                "distance_km": distance_info["distance_km"],
                "duration_minutes": distance_info["duration_minutes"]
            })
    
    # Sort by distance (nearest first)
    chargers_with_distance.sort(key=lambda x: x["distance_km"])
    
    # Return only the requested number of nearest chargers
    return {
        "user_location": {"latitude": lat, "longitude": lon},
        "total_chargers_found": len(chargers_with_distance),
        "nearest_chargers": chargers_with_distance[:limit]
    }