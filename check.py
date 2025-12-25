# check_database.py
from app.database import SessionLocal
from app.models import Charger
from sqlalchemy import func

db = SessionLocal()

# Count total chargers
total = db.query(Charger).count()
print(f"Total chargers in database: {total}")

# Check for duplicates by location
duplicates = db.query(
    Charger.latitude,
    Charger.longitude,
    Charger.name,
    func.count(Charger.id).label('count')
).group_by(
    Charger.latitude,
    Charger.longitude,
    Charger.name
).having(
    func.count(Charger.id) > 1
).all()

if duplicates:
    print(f"\n⚠️  Found {len(duplicates)} duplicate locations:")
    for lat, lon, name, count in duplicates:
        print(f"  - {name} at ({lat}, {lon}): {count} times")
else:
    print("\n✅ No duplicates found!")

# Show all chargers
print(f"\n{'='*70}")
print(f"All chargers in database:")
print(f"{'='*70}")
chargers = db.query(Charger).all()
for i, charger in enumerate(chargers, 1):
    print(f"{i}. {charger.name} - {charger.city} ({charger.latitude}, {charger.longitude})")

db.close()

print(f"\n{'='*70}")
print(f"Summary: {total} total records")
if total > 27:
    print(f"⚠️  You have {total - 27} extra records (duplicates)")
elif total < 27:
    print(f"⚠️  You're missing {27 - total} stations")
else:
    print("✅ Perfect! Exactly 27 stations as expected")