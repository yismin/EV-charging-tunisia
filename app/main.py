#use: uvicorn app.main:app --reload
import json
from app.models import User
from app.models import Review
from app.models import Charger
from app.models import Vehicle
from app.models import Favorite
from app.models import Trip
from app.auth_utils import member_required
from app.auth_utils import hash_password, verify_password
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.auth_utils import create_access_token
from app.auth_utils import member_required
from sqlalchemy.orm import Session
from app.database import SessionLocal, Base, engine
import requests
import os
import math
from dotenv import load_dotenv

load_dotenv()
OPENROUTESERVICE_API_KEY = os.getenv("OPENROUTESERVICE_API_KEY")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="EV Charging API")

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
    connector_type: str | None = Query(None),
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
    
    if connector_type:
        ct = connector_type.lower().replace(" ", "").replace("-", "")
        chargers = [
            c for c in chargers
            if c.connector_type
            and ct in c.connector_type.lower().replace(" ", "").replace("-", "")
        ]
    if not chargers:
        raise HTTPException(status_code=404, detail="No chargers found")

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

@app.post("/auth/register")
def register(email: str, password: str, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == email).first()
    
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=email,
        hashed_password=hash_password(password)
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {"message": "Account created successfully"}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

@app.post("/auth/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(
        data={"user_id": user.id, "role": user.role}
    )

    return {
        "access_token": token,
        "token_type": "bearer"
    }

@app.get("/users/me")
def get_my_profile(user=Depends(member_required)):
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role
    }

@app.post("/chargers/{charger_id}/reviews")
def add_review(
    charger_id: int,
    rating: int,
    comment: str | None = None,
    user=Depends(member_required),
    db: Session = Depends(get_db)
):
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")

    review = Review(
        rating=rating,
        comment=comment,
        user_id=user.id,
        charger_id=charger_id
    )

    db.add(review)
    db.commit()
    db.refresh(review)

    return {"message": "Review added successfully"}

@app.get("/chargers/{charger_id}/reviews")
def get_reviews(charger_id: int, db: Session = Depends(get_db)):
    return db.query(Review).filter(Review.charger_id == charger_id).all()

@app.post("/users/me/vehicle")
def add_or_update_vehicle(
    connector_type: str,
    range_km: float | None = None,
    user=Depends(member_required),
    db: Session = Depends(get_db)
):
    vehicle = db.query(Vehicle).filter(
        Vehicle.user_id == user.id
    ).first()

    if vehicle:
        vehicle.connector_type = connector_type
        vehicle.range_km = range_km
    else:
        vehicle = Vehicle(
            user_id=user.id,
            connector_type=connector_type,
            range_km=range_km
        )
        db.add(vehicle)

    db.commit()
    return {"message": "Vehicle saved successfully"}

@app.get("/users/me/vehicle")
def get_my_vehicle(
    user=Depends(member_required),
    db: Session = Depends(get_db)
):
    return db.query(Vehicle).filter(
        Vehicle.user_id == user.id
    ).first()

@app.post("/favorites/{charger_id}")
def add_favorite(
    charger_id: int,
    user=Depends(member_required),
    db: Session = Depends(get_db)
):
    # Check charger exists
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")

    # Check duplicate
    existing = db.query(Favorite).filter(
        Favorite.user_id == user.id,
        Favorite.charger_id == charger_id
    ).first()

    if existing:
        return {"message": "Charger already in favorites"}

    favorite = Favorite(
        user_id=user.id,
        charger_id=charger_id
    )

    db.add(favorite)
    db.commit()

    return {"message": "Charger added to favorites"}

@app.delete("/favorites/{charger_id}")
def remove_favorite(
    charger_id: int,
    user=Depends(member_required),
    db: Session = Depends(get_db)
):
    favorite = db.query(Favorite).filter(
        Favorite.user_id == user.id,
        Favorite.charger_id == charger_id
    ).first()

    if not favorite:
        raise HTTPException(status_code=404, detail="Favorite not found")

    db.delete(favorite)
    db.commit()

    return {"message": "Charger removed from favorites"}

@app.get("/favorites")
def get_my_favorites(
    user=Depends(member_required),
    db: Session = Depends(get_db)
):
    favorites = db.query(Favorite).filter(
        Favorite.user_id == user.id
    ).all()

    charger_ids = [f.charger_id for f in favorites]

    chargers = db.query(Charger).filter(
        Charger.id.in_(charger_ids)
    ).all()

    return chargers

@app.get("/favorites/check/{charger_id}")
def check_favorite(
    charger_id: int,
    user=Depends(member_required),
    db: Session = Depends(get_db)
):
    exists = db.query(Favorite).filter(
        Favorite.user_id == user.id,
        Favorite.charger_id == charger_id
    ).first()

    return {
        "charger_id": charger_id,
        "is_favorite": exists is not None
    }

def midpoint(lat1, lon1, lat2, lon2):
    return (lat1 + lat2) / 2, (lon1 + lon2) / 2


def find_nearest_compatible_charger(
    lat: float,
    lon: float,
    connector_type: str,
    db: Session,
    max_distance_km: float = 50
):
    chargers = db.query(Charger).all()

    ct = connector_type.lower().replace(" ", "").replace("-", "")

    compatible = [
        c for c in chargers
        if c.connector_type
        and ct in c.connector_type.lower().replace(" ", "").replace("-", "")
    ]

    closest = None
    min_dist = None

    for c in compatible:
        d = haversine_distance(lat, lon, c.latitude, c.longitude)
        if d <= max_distance_km and (min_dist is None or d < min_dist):
            closest = c
            min_dist = d

    return closest

@app.post("/trips/plan")
def plan_trip(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    user=Depends(member_required),
    db: Session = Depends(get_db)
):
    vehicle = db.query(Vehicle).filter(
        Vehicle.user_id == user.id
    ).first()

    if not vehicle or not vehicle.range_km or not vehicle.connector_type:
        raise HTTPException(
            status_code=400,
            detail="Vehicle with range and connector type required"
        )

    driving = calculate_driving_distance(
        start_lat, start_lon, end_lat, end_lon
    )

    if not driving:
        raise HTTPException(status_code=400, detail="Route calculation failed")

    total_distance = driving["distance_km"]
    duration = driving["duration_minutes"]

    waypoints = []

    if total_distance > vehicle.range_km:
        mid_lat, mid_lon = midpoint(
            start_lat, start_lon, end_lat, end_lon
        )

        charger = find_nearest_compatible_charger(
            mid_lat,
            mid_lon,
            vehicle.connector_type,
            db
        )

        if charger:
            waypoints.append({
                "id": charger.id,
                "name": charger.name,
                "latitude": charger.latitude,
                "longitude": charger.longitude
            })

    trip = Trip(
        user_id=user.id,
        start_lat=start_lat,
        start_lon=start_lon,
        end_lat=end_lat,
        end_lon=end_lon,
        waypoints=json.dumps(waypoints),
        total_distance_km=total_distance,
        estimated_duration_minutes=duration
    )

    db.add(trip)
    db.commit()
    db.refresh(trip)

    return trip

@app.get("/trips")
def get_my_trips(
    user=Depends(member_required),
    db: Session = Depends(get_db)
):
    return db.query(Trip).filter(
        Trip.user_id == user.id
    ).order_by(Trip.created_at.desc()).all()

@app.delete("/trips/{trip_id}")
def delete_trip(
    trip_id: int,
    user=Depends(member_required),
    db: Session = Depends(get_db)
):
    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.user_id == user.id
    ).first()

    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    db.delete(trip)
    db.commit()

    return {"message": "Trip deleted"}
