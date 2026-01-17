from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime

# User Schemas
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    
    class Config:
        from_attributes = True

# Charger Schemas
class ChargerBase(BaseModel):
    name: str
    city: str
    latitude: float
    longitude: float
    usage_type: str
    connector_type: str

class ChargerResponse(BaseModel):
    id: int
    name: str
    city: str
    latitude: float
    longitude: float
    usage_type: str
    connector_type: str
    status: str = "unknown"
    avg_rating: float | None = None
    review_count: int = 0
    report_count: int = 0
    
    class Config:
        from_attributes = True

class ChargerWithDistance(ChargerResponse):
    distance_km: float
    duration_minutes: float | None = None
    distance_type: str = "driving"

# Review Schemas
class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(None, max_length=500)

class ReviewUpdate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(None, max_length=500)

class ReviewResponse(BaseModel):
    id: int
    rating: int
    comment: str | None
    user_id: int
    charger_id: int
    created_at: datetime | None = None
    helpful_count: int = 0
    
    class Config:
        from_attributes = True

# Vehicle Schemas
class VehicleCreate(BaseModel):
    connector_type: str
    range_km: float | None = Field(None, gt=0, description="Vehicle range in kilometers")

class VehicleResponse(BaseModel):
    id: int
    user_id: int
    connector_type: str
    range_km: float | None
    
    class Config:
        from_attributes = True

# Trip Schemas
class TripCreate(BaseModel):
    start_lat: float = Field(..., ge=-90, le=90)
    start_lon: float = Field(..., ge=-180, le=180)
    end_lat: float = Field(..., ge=-90, le=90)
    end_lon: float = Field(..., ge=-180, le=180)

class TripResponse(BaseModel):
    id: int
    user_id: int
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    waypoints: str
    total_distance_km: float | None
    estimated_duration_minutes: float | None
    created_at: datetime | None
    
    class Config:
        from_attributes = True

# Report Schema
class ChargerReportCreate(BaseModel):
    issue_type: str = Field(..., pattern="^(broken|working|occupied|under_construction)$")
    description: str = Field(..., min_length=1, max_length=500)

# Pagination Response
class PaginatedResponse(BaseModel):
    total: int
    skip: int
    limit: int
    results: list

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"