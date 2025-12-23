# data_fetch.py
import requests
import os
from dotenv import load_dotenv
from app.models import Charger, Base
from app.database import SessionLocal, engine

load_dotenv()
API_KEY = os.getenv("OPENCHARGEMAP_API_KEY")

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

def fetch_chargers(country_code="TN", max_results=100):
    url = "https://api.openchargemap.io/v3/poi/"
    params = {"countrycode": country_code, "maxresults": max_results, "key": API_KEY}
    response = requests.get(url, params=params)
    return response.json()

def save_chargers_to_db(data):
    db = SessionLocal()
    for item in data:
        info = item.get("AddressInfo", {})
        usage = item.get("UsageType", {})
        charger = Charger(
            name=info.get("Title", "Unknown"),
            city=info.get("Town", "Unknown"),
            latitude=info.get("Latitude", 0),
            longitude=info.get("Longitude", 0),
            usage_type=usage.get("Title", "Unknown")
        )
        db.add(charger)
    db.commit()
    db.close()

if __name__ == "__main__":
    chargers = fetch_chargers()
    save_chargers_to_db(chargers)
    print(f"Saved {len(chargers)} chargers to the database!")
