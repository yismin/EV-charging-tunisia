# main.py - OPTIMIZED VERSION
from fastapi import FastAPI, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal, Base, engine
from app.models import Charger
import requests
import os
import math
from dotenv import load_dotenv

load_dotenv()
OPENROUTESERVICE_API_KEY = os.getenv("OPENROUTESERVICE_API_KEY")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="TuniCharge API")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate straight-line distance between two points in kilometers."""
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    distance = R * c
    
    return round(distance, 2)


def calculate_driving_distance(start_lat: float, start_lon: float, 
                                end_lat: float, end_lon: float) -> dict:
    """
    Calculate driving distance using OpenRouteService API.
    Returns None if API fails (no fallback here - we'll handle it separately).
    """
    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    
    headers = {
        "Authorization": OPENROUTESERVICE_API_KEY
    }
    
    params = {
        "start": f"{start_lon},{start_lat}",
        "end": f"{end_lon},{end_lat}"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        summary = data["features"][0]["properties"]["summary"]
        distance_meters = summary["distance"]
        duration_seconds = summary["duration"]
        
        return {
            "distance_km": round(distance_meters / 1000, 2),
            "duration_minutes": round(duration_seconds / 60, 1)
        }
    except Exception as e:
        print(f"API error: {e}")
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
    radius_km: float = Query(100, description="Search radius in kilometers", ge=1, le=500),
    db: Session = Depends(get_db)
):
    """
    Find nearest chargers - OPTIMIZED VERSION.
    
    Strategy:
    1. Calculate straight-line distance to ALL chargers (fast, no API)
    2. Filter to only those within radius_km
    3. Only call routing API for the filtered set (much fewer calls)
    4. Sort by driving distance and return top results
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
    
    # STEP 1: Calculate straight-line distance to ALL chargers (instant)
    chargers_with_straight_distance = []
    for charger in chargers:
        straight_distance = haversine_distance(lat, lon, charger.latitude, charger.longitude)
        chargers_with_straight_distance.append({
            "charger": charger,
            "straight_distance_km": straight_distance
        })
    
    # STEP 2: Filter to only chargers within the radius
    nearby_chargers = [
        c for c in chargers_with_straight_distance 
        if c["straight_distance_km"] <= radius_km
    ]
    
    # Sort by straight-line distance
    nearby_chargers.sort(key=lambda x: x["straight_distance_km"])
    
    # STEP 3: Only calculate driving distance for the NEAREST ones
    # Limit to max 10 API calls even if more are nearby
    max_api_calls = min(limit * 2, 10)  # Calculate for 2x the requested limit, max 10
    chargers_to_route = nearby_chargers[:max_api_calls]
    
    result_chargers = []
    
    for item in chargers_to_route:
        charger = item["charger"]
        straight_dist = item["straight_distance_km"]
        
        # Try to get driving distance
        driving_info = calculate_driving_distance(lat, lon, charger.latitude, charger.longitude)
        
        if driving_info:
            # We got driving distance successfully
            result_chargers.append({
                "id": charger.id,
                "name": charger.name,
                "city": charger.city,
                "latitude": charger.latitude,
                "longitude": charger.longitude,
                "usage_type": charger.usage_type,
                "distance_km": driving_info["distance_km"],
                "duration_minutes": driving_info["duration_minutes"],
                "distance_type": "driving"
            })
        else:
            # API failed, use straight-line distance as fallback
            result_chargers.append({
                "id": charger.id,
                "name": charger.name,
                "city": charger.city,
                "latitude": charger.latitude,
                "longitude": charger.longitude,
                "usage_type": charger.usage_type,
                "distance_km": straight_dist,
                "duration_minutes": round((straight_dist / 50) * 60, 1),  # Estimate
                "distance_type": "straight_line"
            })
    
    # Sort by actual distance (driving or straight-line)
    result_chargers.sort(key=lambda x: x["distance_km"])
    
    # Return requested number
    return {
        "user_location": {"latitude": lat, "longitude": lon},
        "search_radius_km": radius_km,
        "total_within_radius": len(nearby_chargers),
        "returned_with_routes": len(result_chargers),
        "nearest_chargers": result_chargers[:limit]
    }


@app.get("/chargers/nearby-fast")
def get_nearby_chargers_fast(
    lat: float = Query(..., description="User's current latitude"),
    lon: float = Query(..., description="User's current longitude"),
    limit: int = Query(10, description="Number of nearest chargers to return", ge=1, le=27),
    db: Session = Depends(get_db)
):
    """
    SUPER FAST version - only uses straight-line distance, no routing API.
    Perfect for quick searches when exact driving distance isn't critical.
    
    Response time: < 100ms
    """
    # Validate coordinates
    if not (-90 <= lat <= 90):
        raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90")
    if not (-180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180")
    
    # Get all chargers
    chargers = db.query(Charger).all()
    
    if not chargers:
        raise HTTPException(status_code=404, detail="No chargers found in database")
    
    # Calculate straight-line distance for all
    chargers_with_distance = []
    for charger in chargers:
        distance_km = haversine_distance(lat, lon, charger.latitude, charger.longitude)
        chargers_with_distance.append({
            "id": charger.id,
            "name": charger.name,
            "city": charger.city,
            "latitude": charger.latitude,
            "longitude": charger.longitude,
            "usage_type": charger.usage_type,
            "distance_km": distance_km,
            "duration_minutes": round((distance_km / 50) * 60, 1),  # Rough estimate
            "distance_type": "straight_line"
        })
    
    # Sort by distance
    chargers_with_distance.sort(key=lambda x: x["distance_km"])
    
    return {
        "user_location": {"latitude": lat, "longitude": lon},
        "total_chargers": len(chargers_with_distance),
        "nearest_chargers": chargers_with_distance[:limit],
        "note": "Distances are straight-line. Use /chargers/nearby for driving distances."
    }