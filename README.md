# ⚡ Volty - EV Charging Tunisia

A community-driven platform for finding and sharing electric vehicle charging stations across Tunisia. Built with FastAPI and Streamlit.

![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

##  Features

### For EV Drivers
-  **Find Charging Stations** - Search by location, connector type, and status
-  **Interactive Maps** - View stations on an interactive map with real-time status
-  **Favorites** - Save your frequently used charging stations
-  **Trip Planning** - Plan routes with automatic charging stop recommendations
-  **Statistics** - Track your trips, distance traveled, and CO₂ saved

### Community Features
- **Reviews & Ratings** - Share your experience with other EV drivers
- **Status Reports** - Report if a charger is working, broken, or occupied
- **Collaborative Data** - Community-driven status updates

### Technical Features
-  **Secure Authentication** - JWT-based user authentication
-  **Fast API** - Built with FastAPI for high performance
-  **Docker Ready** - Easy deployment with Docker Compose
-  **Responsive UI**  

##  Prerequisites

- Python 3.11+
- Docker & Docker Compose  
- API Keys:
  - OpenChargeMap API Key ([Get it here](https://openchargemap.org/site/develop/api))
  - OpenRouteService API Key ([Get it here](https://openrouteservice.org/dev/#/signup))

##  Quick Start

### Option 1: Docker (Recommended)

1. **Clone the repository**
```bash
git clone <your-repo-url>
cd ev-charging-tunisia
```

2. **Create environment file**
```bash
cp .env.example .env
```

Edit `.env` and add your API keys:
```env
DATABASE_URL=sqlite:////app/ev_charging.db
SECRET_KEY=your-super-secret-key-here
OPENCHARGEMAP_API_KEY=your-openchargemap-key
OPENROUTESERVICE_API_KEY=your-openrouteservice-key
```

3. **Run with Docker Compose**
```bash
docker-compose up -d
```

4. **Access the application**
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Frontend: Run `streamlit run streamlit_app.py`

### Option 2: Manual Setup

1. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Create `.env` file** (same as Docker option)

4. **Initialize database**
```bash
python app/data_fetch.py
```

5. **Run the API**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

6. **Run the frontend** (in a new terminal)
```bash
streamlit run streamlit_app.py
```

## Database Schema

### Core Models

**Charger**
- Location and contact info
- Connector types
- Real-time status (working/broken/occupied)
- Usage type (public/private)

**User**
- Email and hashed password
- Role-based access
- Statistics tracking

**Review**
- Rating (1-5 stars)
- Comments
- Helpful votes

**Vehicle**
- Connector type
- Range (km)

**Trip**
- Start/end coordinates
- Charging stops
- Distance and duration

**ChargerReport**
- Issue type
- Description
- Community status updates

##  API Endpoints

### Authentication
- `POST /auth/register` - Register new user
- `POST /auth/login` - Login and get JWT token

### Chargers
- `GET /chargers` - List all chargers  
- `GET /chargers/search` - Search with filters
- `GET /chargers/nearby` - Find nearby chargers
- `GET /chargers/{id}` - Get charger details

### Reviews
- `POST /chargers/{id}/reviews` - Add review
- `GET /chargers/{id}/reviews` - Get reviews
- `PUT /reviews/{id}` - Update review
- `DELETE /reviews/{id}` - Delete review

### User Features
- `GET /users/me` - Get profile
- `GET /users/me/stats` - Get statistics
- `POST /users/me/vehicle` - Save vehicle info
- `GET /favorites` - Get favorite chargers
- `POST /favorites/{id}` - Add to favorites

### Trip Planning
- `POST /trips/plan` - Plan trip with charging stops
- `GET /trips` - Get trip history

### Reports
- `POST /chargers/{id}/report` - Report charger status
- `GET /chargers/{id}/reports` - View reports

## Testing

Run tests:
```bash
python -m pytest test.py -v
```

Run with coverage:
```bash
pytest --cov=app test.py
```


##  Future Enhancements

- [ ] Mobile app (React Native)
- [ ] Payment integration for paid chargers
- [ ] Real-time charger availability
- [ ] Charger reservation system
- [ ] Admin dashboard
- [ ] Multi-language support (Arabic/French)
- [ ] Push notifications for charger status
- [ ] Social features (EV driver community)


## Acknowledgments
- OpenChargeMap for charging station data
- OpenRouteService for route calculations
- FastAPI community for excellent documentation
- Streamlit for the framework

