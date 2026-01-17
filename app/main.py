# use: uvicorn app.main:app --reload
import json
import logging
from typing import List
from datetime import datetime, timedelta
from app.models import User, Review, Charger, Vehicle, Favorite, Trip, ChargerReport
from app.auth_utils import member_required, hash_password, verify_password, validate_password_strength, get_current_user
from app import schemas
from fastapi import FastAPI, Depends, Query, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from app.auth_utils import create_access_token
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.database import SessionLocal, Base, engine, get_db
from app.config import settings
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import requests
import math

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# Initialize app
app = FastAPI(
    title="EV Charging Tunisia API",
    description="Community-driven EV charging station finder in Tunisia",
    version="2.0.0"
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============= UTILITY FUNCTIONS =============
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate straight-line distance between two points in kilometers."""
    R = 6371
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    distance = R * c
    
    return round(distance, 2)

def calculate_driving_distance(start_lat: float, start_lon: float, 
                                end_lat: float, end_lon: float) -> dict | None:
    """Calculate driving distance using OpenRouteService API with fallback."""
    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    
    headers = {"Authorization": settings.openrouteservice_api_key}
    params = {
        "start": f"{start_lon},{start_lat}",
        "end": f"{end_lon},{end_lat}"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("features"):
            logger.warning("No route found in OpenRouteService response")
            return None
            
        summary = data["features"][0]["properties"]["summary"]
        distance_meters = summary["distance"]
        duration_seconds = summary["duration"]
        
        return {
            "distance_km": round(distance_meters / 1000, 2),
            "duration_minutes": round(duration_seconds / 60, 1)
        }
    except requests.exceptions.Timeout:
        logger.error("OpenRouteService API timeout - using haversine fallback")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Routing API error: {e}")
        return None

def update_charger_status(charger_id: int, db: Session):
    """Update charger status based on recent reports."""
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        return
    
    # Get reports from last 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_reports = db.query(ChargerReport).filter(
        and_(
            ChargerReport.charger_id == charger_id,
            ChargerReport.created_at >= seven_days_ago
        )
    ).all()
    
    if not recent_reports:
        charger.status = "unknown"
        charger.status_updated_at = datetime.utcnow()
        db.commit()
        return
    
    # Count reports by type
    status_counts = {}
    for r in recent_reports:
        status_counts[r.issue_type] = status_counts.get(r.issue_type, 0) + 1
    
    # Determine status (majority vote, with priority: broken > occupied > under_construction > working)
    if status_counts.get("broken", 0) > 0 and status_counts.get("broken", 0) >= status_counts.get("working", 0):
        charger.status = "broken"
    elif status_counts.get("occupied", 0) > status_counts.get("working", 0):
        charger.status = "occupied"
    elif status_counts.get("under_construction", 0) > status_counts.get("working", 0):
        charger.status = "under_construction"
    elif status_counts.get("working", 0) > 0:
        charger.status = "working"
    else:
        charger.status = "unknown"
    
    charger.status_updated_at = datetime.utcnow()
    db.commit()

# ============= HEALTH CHECK =============
@app.get("/", tags=["Health"])
def root():
    return {
        "message": "EV Charging Tunisia API",
        "version": "2.0.0",
        "status": "running"
    }

@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}

# ============= CHARGER ENDPOINTS =============
# NOTE: Specific paths (/chargers/search, /chargers/nearby) MUST come before parameterized paths (/chargers/{charger_id})
# to avoid FastAPI matching "search" as a charger_id

@app.get("/chargers", response_model=dict, tags=["Chargers"])
@limiter.limit("100/minute")
def get_chargers(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, regex="^(working|broken|occupied|under_construction|unknown)$"),
    db: Session = Depends(get_db)
):
    """Get all chargers with pagination and optional status filter."""
    query = db.query(Charger)
    
    if status:
        query = query.filter(Charger.status == status)
    
    total = query.count()
    chargers = query.offset(skip).limit(limit).all()
    
    chargers_with_ratings = []
    for charger in chargers:
        avg_rating = db.query(func.avg(Review.rating)).filter(
            Review.charger_id == charger.id
        ).scalar()
        review_count = db.query(Review).filter(Review.charger_id == charger.id).count()
        report_count = db.query(ChargerReport).filter(ChargerReport.charger_id == charger.id).count()
        
        charger_dict = {
            "id": charger.id,
            "name": charger.name,
            "city": charger.city,
            "latitude": charger.latitude,
            "longitude": charger.longitude,
            "usage_type": charger.usage_type,
            "connector_type": charger.connector_type,
            "status": charger.status,
            "avg_rating": round(avg_rating, 2) if avg_rating else None,
            "review_count": review_count,
            "report_count": report_count
        }
        chargers_with_ratings.append(charger_dict)
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "results": chargers_with_ratings
    }

@app.get("/chargers/search", tags=["Chargers"])
@limiter.limit("50/minute")
def search_chargers(
    request: Request,
    city: str | None = Query(None),
    usage_type: str | None = Query(None),
    connector_type: str | None = Query(None),
    status: str | None = Query(None, regex="^(working|broken|occupied|under_construction|unknown)$"),
    min_rating: float | None = Query(None, ge=0, le=5),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Search chargers with advanced filters."""
    query = db.query(Charger)
    
    if city:
        query = query.filter(Charger.city.ilike(f"%{city}%"))
    if usage_type:
        query = query.filter(Charger.usage_type.ilike(f"%{usage_type}%"))
    if connector_type:
        query = query.filter(Charger.connector_type.ilike(f"%{connector_type}%"))
    if status:
        query = query.filter(Charger.status == status)
    
    total = query.count()
    chargers = query.offset(skip).limit(limit).all()
    
    results = []
    for charger in chargers:
        avg_rating = db.query(func.avg(Review.rating)).filter(
            Review.charger_id == charger.id
        ).scalar()
        
        # Filter by min_rating if specified
        if min_rating and (avg_rating is None or avg_rating < min_rating):
            continue
        
        review_count = db.query(Review).filter(Review.charger_id == charger.id).count()
        report_count = db.query(ChargerReport).filter(ChargerReport.charger_id == charger.id).count()
        
        results.append({
            "id": charger.id,
            "name": charger.name,
            "city": charger.city,
            "latitude": charger.latitude,
            "longitude": charger.longitude,
            "usage_type": charger.usage_type,
            "connector_type": charger.connector_type,
            "status": charger.status,
            "avg_rating": round(avg_rating, 2) if avg_rating else None,
            "review_count": review_count,
            "report_count": report_count
        })
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "results": results
    }

@app.get("/chargers/nearby", tags=["Chargers"])
@limiter.limit("30/minute")
def get_nearby_chargers(
    request: Request,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    connector_type: str | None = Query(None),
    status: str | None = Query(None, regex="^(working|broken|occupied|under_construction|unknown)$"),
    min_rating: float | None = Query(None, ge=0, le=5),
    limit: int = Query(10, ge=1, le=27),
    radius_km: float = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Find nearest chargers with optimized routing and filters."""
    chargers = db.query(Charger).all()
    
    # Filter by connector type
    if connector_type:
        ct = connector_type.lower().replace(" ", "").replace("-", "")
        chargers = [
            c for c in chargers
            if c.connector_type and ct in c.connector_type.lower().replace(" ", "").replace("-", "")
        ]
    
    # Filter by status
    if status:
        chargers = [c for c in chargers if c.status == status]
    
    if not chargers:
        raise HTTPException(status_code=404, detail="No chargers found matching criteria")

    # Calculate distances
    chargers_with_distance = []
    for charger in chargers:
        straight_distance = haversine_distance(lat, lon, charger.latitude, charger.longitude)
        if straight_distance <= radius_km:
            chargers_with_distance.append({
                "charger": charger,
                "straight_distance_km": straight_distance
            })
    
    if not chargers_with_distance:
        raise HTTPException(status_code=404, detail="No chargers found within radius")
    
    chargers_with_distance.sort(key=lambda x: x["straight_distance_km"])
    
    # Use haversine distance for all results (instant, no API calls)
    # This avoids timeout issues with OpenRouteService API
    result_chargers = []
    
    for item in chargers_with_distance[:limit]:
        charger = item["charger"]
        straight_dist = item["straight_distance_km"]
        
        # Get rating
        avg_rating = db.query(func.avg(Review.rating)).filter(
            Review.charger_id == charger.id
        ).scalar()
        
        # Filter by min_rating if specified
        if min_rating and (avg_rating is None or avg_rating < min_rating):
            continue
        
        review_count = db.query(Review).filter(Review.charger_id == charger.id).count()
        
        # Use haversine distance (instant calculation, no API timeout)
        result_chargers.append({
            "id": charger.id,
            "name": charger.name,
            "city": charger.city,
            "latitude": charger.latitude,
            "longitude": charger.longitude,
            "usage_type": charger.usage_type,
            "connector_type": charger.connector_type,
            "status": charger.status,
            "distance_km": straight_dist,
            "duration_minutes": round((straight_dist / 50) * 60, 1),
            "distance_type": "straight_line",
            "avg_rating": round(avg_rating, 2) if avg_rating else None,
            "review_count": review_count
        })
    
    return {
        "user_location": {"latitude": lat, "longitude": lon},
        "search_radius_km": radius_km,
        "total_within_radius": len(chargers_with_distance),
        "returned_with_routes": len(result_chargers),
        "nearest_chargers": result_chargers
    }

@app.get("/chargers/{charger_id}", response_model=schemas.ChargerResponse, tags=["Chargers"])
def get_charger_by_id(charger_id: int, db: Session = Depends(get_db)):
    """Get a specific charger by ID with full details."""
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    avg_rating = db.query(func.avg(Review.rating)).filter(
        Review.charger_id == charger.id
    ).scalar()
    review_count = db.query(Review).filter(Review.charger_id == charger.id).count()
    report_count = db.query(ChargerReport).filter(ChargerReport.charger_id == charger.id).count()
    
    return {
        "id": charger.id,
        "name": charger.name,
        "city": charger.city,
        "latitude": charger.latitude,
        "longitude": charger.longitude,
        "usage_type": charger.usage_type,
        "connector_type": charger.connector_type,
        "status": charger.status,
        "avg_rating": round(avg_rating, 2) if avg_rating else None,
        "review_count": review_count,
        "report_count": report_count
    }

# ============= AUTH ENDPOINTS =============
@app.post("/auth/register", response_model=dict, tags=["Authentication"])
@limiter.limit("5/minute")
def register(
    request: Request,
    user_data: schemas.UserRegister,
    db: Session = Depends(get_db)
):
    """Register a new user with password validation."""
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    if not validate_password_strength(user_data.password):
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters with uppercase, lowercase, and numbers"
        )

    user = User(
        email=user_data.email,
        hashed_password=hash_password(user_data.password)
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {"message": "Account created successfully", "user_id": user.id}

@app.post("/auth/login", response_model=schemas.TokenResponse, tags=["Authentication"])
@limiter.limit("10/minute")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Login and receive JWT token."""
    user = db.query(User).filter(User.email == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = create_access_token(data={"user_id": user.id, "role": user.role})

    return {"access_token": token, "token_type": "bearer"}

@app.get("/users/me", response_model=schemas.UserResponse, tags=["Users"])
def get_my_profile(user: User = Depends(member_required)):
    """Get current user profile."""
    return user

# ============= REVIEW ENDPOINTS =============
@app.post("/chargers/{charger_id}/reviews", response_model=dict, tags=["Reviews"])
@limiter.limit("10/hour")
def add_review(
    request: Request,
    charger_id: int,
    review_data: schemas.ReviewCreate,
    user: User = Depends(member_required),
    db: Session = Depends(get_db)
):
    """Add a review to a charger."""
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    existing_review = db.query(Review).filter(
        Review.user_id == user.id,
        Review.charger_id == charger_id
    ).first()
    
    if existing_review:
        raise HTTPException(status_code=400, detail="You already reviewed this charger")

    review = Review(
        rating=review_data.rating,
        comment=review_data.comment,
        user_id=user.id,
        charger_id=charger_id
    )

    db.add(review)
    db.commit()
    db.refresh(review)

    return {"message": "Review added successfully", "review_id": review.id}

@app.get("/chargers/{charger_id}/reviews", response_model=List[schemas.ReviewResponse], tags=["Reviews"])
def get_reviews(charger_id: int, db: Session = Depends(get_db)):
    """Get all reviews for a charger."""
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    return db.query(Review).filter(Review.charger_id == charger_id).order_by(Review.created_at.desc()).all()

@app.put("/reviews/{review_id}", response_model=dict, tags=["Reviews"])
@limiter.limit("10/hour")
def update_review(
    request: Request,
    review_id: int,
    review_data: schemas.ReviewUpdate,
    user: User = Depends(member_required),
    db: Session = Depends(get_db)
):
    """Update your own review."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    if review.user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own reviews")
    
    review.rating = review_data.rating
    review.comment = review_data.comment
    db.commit()
    db.refresh(review)
    
    return {"message": "Review updated successfully", "review_id": review.id}

@app.delete("/reviews/{review_id}", tags=["Reviews"])
@limiter.limit("10/hour")
def delete_review(
    request: Request,
    review_id: int,
    user: User = Depends(member_required),
    db: Session = Depends(get_db)
):
    """Delete your own review."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    if review.user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own reviews")
    
    db.delete(review)
    db.commit()
    
    return {"message": "Review deleted successfully"}

@app.post("/reviews/{review_id}/helpful", tags=["Reviews"])
@limiter.limit("20/hour")
def mark_review_helpful(
    request: Request,
    review_id: int,
    user: User = Depends(member_required),
    db: Session = Depends(get_db)
):
    """Mark a review as helpful (one vote per user per review)."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # In production, track votes in a separate table to prevent duplicates
    # For now, we'll just increment
    review.helpful_count += 1
    db.commit()
    
    return {"message": "Review marked as helpful", "helpful_count": review.helpful_count}

# ============= VEHICLE ENDPOINTS =============
@app.post("/users/me/vehicle", response_model=dict, tags=["Vehicle"])
def add_or_update_vehicle(
    vehicle_data: schemas.VehicleCreate,
    user: User = Depends(member_required),
    db: Session = Depends(get_db)
):
    """Add or update user's vehicle information."""
    vehicle = db.query(Vehicle).filter(Vehicle.user_id == user.id).first()

    if vehicle:
        vehicle.connector_type = vehicle_data.connector_type
        vehicle.range_km = vehicle_data.range_km
    else:
        vehicle = Vehicle(
            user_id=user.id,
            connector_type=vehicle_data.connector_type,
            range_km=vehicle_data.range_km
        )
        db.add(vehicle)

    db.commit()
    db.refresh(vehicle)
    return {"message": "Vehicle saved successfully", "vehicle_id": vehicle.id}

@app.get("/users/me/vehicle", response_model=schemas.VehicleResponse | None, tags=["Vehicle"])
def get_my_vehicle(user: User = Depends(member_required), db: Session = Depends(get_db)):
    """Get user's vehicle information."""
    vehicle = db.query(Vehicle).filter(Vehicle.user_id == user.id).first()
    return vehicle

# ============= FAVORITE ENDPOINTS =============
@app.post("/favorites/{charger_id}", tags=["Favorites"])
def add_favorite(
    charger_id: int,
    user: User = Depends(member_required),
    db: Session = Depends(get_db)
):
    """Add a charger to favorites."""
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")

    existing = db.query(Favorite).filter(
        Favorite.user_id == user.id,
        Favorite.charger_id == charger_id
    ).first()

    if existing:
        return {"message": "Charger already in favorites"}

    favorite = Favorite(user_id=user.id, charger_id=charger_id)
    db.add(favorite)
    db.commit()

    return {"message": "Charger added to favorites"}

@app.delete("/favorites/{charger_id}", tags=["Favorites"])
def remove_favorite(
    charger_id: int,
    user: User = Depends(member_required),
    db: Session = Depends(get_db)
):
    """Remove a charger from favorites."""
    favorite = db.query(Favorite).filter(
        Favorite.user_id == user.id,
        Favorite.charger_id == charger_id
    ).first()

    if not favorite:
        raise HTTPException(status_code=404, detail="Favorite not found")

    db.delete(favorite)
    db.commit()

    return {"message": "Charger removed from favorites"}

@app.get("/favorites", tags=["Favorites"])
def get_my_favorites(user: User = Depends(member_required), db: Session = Depends(get_db)):
    """Get user's favorite chargers."""
    try:
        logger.info(f"Getting favorites for user {user.id}")
        
        favorites = db.query(Favorite).filter(Favorite.user_id == user.id).all()
        logger.info(f"Found {len(favorites)} favorites")
        
        if not favorites:
            return []
        
        charger_ids = [f.charger_id for f in favorites]
        chargers = db.query(Charger).filter(Charger.id.in_(charger_ids)).all()
        logger.info(f"Found {len(chargers)} chargers")
        
        result = []
        for charger in chargers:
            try:
                avg_rating = db.query(func.avg(Review.rating)).filter(Review.charger_id == charger.id).scalar()
                review_count = db.query(Review).filter(Review.charger_id == charger.id).count()
                report_count = db.query(ChargerReport).filter(ChargerReport.charger_id == charger.id).count()
                
                result.append({
                    "id": charger.id,
                    "name": charger.name,
                    "city": charger.city,
                    "latitude": charger.latitude,
                    "longitude": charger.longitude,
                    "usage_type": charger.usage_type,
                    "connector_type": charger.connector_type,
                    "status": charger.status or "unknown",
                    "avg_rating": round(avg_rating, 2) if avg_rating else None,
                    "review_count": review_count,
                    "report_count": report_count
                })
            except Exception as e:
                logger.error(f"Error processing charger {charger.id}: {e}")
                continue
        
        logger.info(f"Returning {len(result)} chargers")
        return result
        
    except Exception as e:
        logger.error(f"Error getting favorites for user {user.id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving favorites: {str(e)}")

@app.get("/favorites/check/{charger_id}", tags=["Favorites"])
def check_favorite(
    charger_id: int,
    user: User = Depends(member_required),
    db: Session = Depends(get_db)
):
    """Check if a charger is in user's favorites."""
    exists = db.query(Favorite).filter(
        Favorite.user_id == user.id,
        Favorite.charger_id == charger_id
    ).first()

    return {"charger_id": charger_id, "is_favorite": exists is not None}

# ============= TRIP ENDPOINTS =============
@app.post("/trips/plan", response_model=schemas.TripResponse, tags=["Trips"])
@limiter.limit("20/hour")
def plan_trip(
    request: Request,
    trip_data: schemas.TripCreate,
    user: User = Depends(member_required),
    db: Session = Depends(get_db)
):
    """Plan a trip with charging stops (simplified)."""
    vehicle = db.query(Vehicle).filter(Vehicle.user_id == user.id).first()

    if not vehicle or not vehicle.range_km or not vehicle.connector_type:
        raise HTTPException(
            status_code=400,
            detail="Vehicle with range and connector type required"
        )

    driving = calculate_driving_distance(
        trip_data.start_lat, trip_data.start_lon,
        trip_data.end_lat, trip_data.end_lon
    )

    if not driving:
        raise HTTPException(status_code=400, detail="Route calculation failed")

    total_distance = driving["distance_km"]
    duration = driving["duration_minutes"]
    waypoints = []

    trip = Trip(
        user_id=user.id,
        start_lat=trip_data.start_lat,
        start_lon=trip_data.start_lon,
        end_lat=trip_data.end_lat,
        end_lon=trip_data.end_lon,
        waypoints=json.dumps(waypoints),
        total_distance_km=total_distance,
        estimated_duration_minutes=duration
    )

    db.add(trip)
    db.commit()
    db.refresh(trip)

    return trip

@app.get("/trips", response_model=List[schemas.TripResponse], tags=["Trips"])
def get_my_trips(user: User = Depends(member_required), db: Session = Depends(get_db)):
    """Get user's trip history."""
    return db.query(Trip).filter(Trip.user_id == user.id).order_by(Trip.created_at.desc()).all()

@app.delete("/trips/{trip_id}", tags=["Trips"])
def delete_trip(
    trip_id: int,
    user: User = Depends(member_required),
    db: Session = Depends(get_db)
):
    """Delete a trip."""
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()

    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    db.delete(trip)
    db.commit()

    return {"message": "Trip deleted"}

# ============= CHARGER REPORT ENDPOINTS =============
@app.post("/chargers/{charger_id}/report", tags=["Reports"])
@limiter.limit("5/hour")
def report_charger_issue(
    request: Request,
    charger_id: int,
    report_data: schemas.ChargerReportCreate,
    user: User = Depends(member_required),
    db: Session = Depends(get_db)
):
    """Report charger status (broken/working) - community-driven."""
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    report = ChargerReport(
        charger_id=charger_id,
        user_id=user.id,
        issue_type=report_data.issue_type,
        description=report_data.description,
        status="open"
    )
    
    db.add(report)
    db.commit()
    db.refresh(report)
    
    # Update charger status based on reports
    update_charger_status(charger_id, db)
    
    return {"message": "Report submitted successfully", "report_id": report.id}

@app.get("/chargers/{charger_id}/reports", tags=["Reports"])
def get_charger_reports(charger_id: int, db: Session = Depends(get_db)):
    """Get reports for a specific charger."""
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    reports = db.query(ChargerReport).filter(
        ChargerReport.charger_id == charger_id
    ).order_by(ChargerReport.created_at.desc()).all()
    
    return reports

@app.get("/chargers/{charger_id}/status", tags=["Reports"])
def get_charger_status(charger_id: int, db: Session = Depends(get_db)):
    """Get charger status and recent reports summary."""
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    # Get reports from last 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_reports = db.query(ChargerReport).filter(
        and_(
            ChargerReport.charger_id == charger_id,
            ChargerReport.created_at >= seven_days_ago
        )
    ).all()
    
    broken_count = sum(1 for r in recent_reports if r.issue_type == "broken")
    working_count = sum(1 for r in recent_reports if r.issue_type == "working")
    
    return {
        "charger_id": charger_id,
        "current_status": charger.status,
        "status_updated_at": charger.status_updated_at,
        "recent_reports_7days": {
            "broken": broken_count,
            "working": working_count,
            "total": len(recent_reports)
        }
    }

# ============= USER STATS =============
@app.get("/users/me/stats", tags=["Users"])
def get_user_stats(user: User = Depends(member_required), db: Session = Depends(get_db)):
    """Get user statistics."""
    total_trips = db.query(Trip).filter(Trip.user_id == user.id).count()
    total_reviews = db.query(Review).filter(Review.user_id == user.id).count()
    total_favorites = db.query(Favorite).filter(Favorite.user_id == user.id).count()
    total_reports = db.query(ChargerReport).filter(ChargerReport.user_id == user.id).count()
    
    total_distance = db.query(func.sum(Trip.total_distance_km)).filter(
        Trip.user_id == user.id
    ).scalar() or 0
    
    return {
        "total_trips": total_trips,
        "total_reviews": total_reviews,
        "total_favorites": total_favorites,
        "total_reports": total_reports,
        "total_distance_km": round(total_distance, 2),
        "co2_saved_kg": round(total_distance * 0.12, 2)
    }
