"""
Basic API tests for EV Charging Tunisia
Run with: python -m pytest test_basic.py -v
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    """Test API health endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_root_endpoint():
    """Test API root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "version" in data
    assert data["status"] == "running"

def test_get_chargers():
    """Test get chargers endpoint"""
    response = client.get("/chargers?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "results" in data
    assert isinstance(data["results"], list)

def test_charger_search():
    """Test charger search endpoint"""
    response = client.get("/chargers/search?city=Tunis&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "results" in data

def test_register_user():
    """Test user registration"""
    test_user = {
        "email": "test@example.com",
        "password": "TestPass123"
    }
    response = client.post("/auth/register", json=test_user)
    # Should succeed or fail with 400 if user exists
    assert response.status_code in [200, 400]

def test_invalid_login():
    """Test login with invalid credentials"""
    response = client.post("/auth/login", data={
        "username": "invalid@example.com",
        "password": "wrongpassword"
    })
    assert response.status_code == 401

def test_protected_endpoint_without_auth():
    """Test protected endpoint without authentication"""
    response = client.get("/users/me")
    assert response.status_code == 401