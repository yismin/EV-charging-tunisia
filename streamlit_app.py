"""
EV Charging Tunisia - Streamlit Frontend v3.0
Completely rebuilt with working endpoints and proper error handling
"""

import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
import pandas as pd
import json

# ============= CONFIG =============
API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="EV Charging Tunisia",
    page_icon="⚡",
    layout="wide"
)

# ============= SESSION STATE =============
if 'token' not in st.session_state:
    st.session_state.token = None
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'search_results' not in st.session_state:
    st.session_state.search_results = None
if 'filter_results' not in st.session_state:
    st.session_state.filter_results = None

# ============= HELPER FUNCTIONS =============
def get_headers():
    if st.session_state.token:
        return {"Authorization": f"Bearer {st.session_state.token}"}
    return {}

def api_call(method, endpoint, **kwargs):
    """Make API call with proper error handling"""
    try:
        url = f"{API_BASE_URL}{endpoint}"
        headers = kwargs.pop('headers', {})
        headers.update(get_headers())
        
        response = requests.request(method, url, headers=headers, timeout=10, **kwargs)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.ConnectionError:
        return None, "Cannot connect to API. Is it running?"
    except requests.exceptions.Timeout:
        return None, "Request timed out"
    except requests.exceptions.HTTPError as e:
        try:
            error_detail = e.response.json().get('detail', str(e))
        except:
            error_detail = str(e)
        return None, f"API Error: {error_detail}"
    except Exception as e:
        return None, f"Error: {str(e)}"

def create_map(chargers, center_lat=36.8, center_lon=10.1, zoom=7):
    """Create folium map with charger markers"""
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom)
    
    for charger in chargers:
        status = charger.get('status', 'unknown')
        
        # Map status to colors: green=working, red=broken, yellow=under_construction, orange=occupied, gray=unknown
        if status == 'working':
            color = 'green'
        elif status == 'broken':
            color = 'red'
        elif status == 'under_construction':
            color = 'orange'  # folium doesn't have yellow, orange is closest
        elif status == 'occupied':
            color = 'beige'  # folium's beige appears orange-ish
        else:
            color = 'gray'
        
        popup_html = f"""
        <div style="width: 200px;">
            <h4>{charger['name']}</h4>
            <p><b>City:</b> {charger['city']}</p>
            <p><b>Connector:</b> {charger['connector_type']}</p>
            <p><b>Status:</b> {status.replace('_', ' ').title()}</p>
            {f"<p><b>Distance:</b> {charger.get('distance_km', 'N/A')} km</p>" if 'distance_km' in charger else ""}
        </div>
        """
        
        folium.Marker(
            location=[charger['latitude'], charger['longitude']],
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=charger['name'],
            icon=folium.Icon(color=color, icon='plug', prefix='fa')
        ).add_to(m)
    
    return m

# ============= HEADER =============
st.title("⚡ EV Charging Tunisia")
st.markdown("Find the nearest EV charging station in Tunisia")

# ============= SIDEBAR =============
with st.sidebar:
    st.markdown("## Navigation")
    
    if st.session_state.token:
        st.success(f"👤 {st.session_state.user_email}")
        
        page = st.radio("Navigation", [
            "🏠 Home",
            "🔍 Find Chargers",
            "⭐ Favorites",
            "🚗 My Vehicle",
            "🛣️ Plan Trip",
            "📊 Statistics",
            "📝 Write Review",
            "🚨 Report Charger"
        ], label_visibility="collapsed")
        
        if st.button("🚪 Logout"):
            st.session_state.token = None
            st.session_state.user_email = None
            st.rerun()
    else:
        page = st.radio("Navigation", [
            "🏠 Home",
            "🔍 Find Chargers",
            "🔐 Login",
            "📝 Register"
        ], label_visibility="collapsed")

# ============= HOME PAGE =============
if page == "🏠 Home":
    # Get charger count
    data, error = api_call("GET", "/chargers?limit=1")
    total_chargers = data.get('total', 0) if data else 0
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📍 Stations", total_chargers)
    with col2:
        st.metric("🌍 Coverage", "Tunisia")
    with col3:
        st.metric("✅ Status", "Online")
    
    st.markdown("---")
    st.markdown("## 📍 All Charging Stations")
    
    # Load all chargers
    data, error = api_call("GET", "/chargers?limit=100")
    if error:
        st.error(f"Error loading chargers: {error}")
    elif data and data.get('results'):
        chargers = data['results']
        st.info(f"Showing {len(chargers)} charging stations")
        m = create_map(chargers)
        st_folium(m, width=None, height=500)
    else:
        st.warning("No chargers found")

# ============= FIND CHARGERS =============
elif page == "🔍 Find Chargers":
    st.markdown("## 🔍 Find Charging Stations")
    
    search_mode = st.radio("Search by:", ["📍 Location", "🔎 Filters"], horizontal=True)
    
    if search_mode == "📍 Location":
        col1, col2 = st.columns(2)
        with col1:
            lat = st.number_input("Latitude", value=36.8, format="%.6f")
        with col2:
            lon = st.number_input("Longitude", value=10.1, format="%.6f")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            radius = st.slider("Radius (km)", 1, 200, 50)
        with col2:
            limit = st.slider("Max Results", 1, 27, 10)
        with col3:
            status = st.selectbox("Status", ["All", "working", "broken", "occupied", "under_construction", "unknown"])
        
        connector = st.text_input("Connector Type (optional)", placeholder="e.g., Type 2")
        
        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            search_clicked = st.button("🔍 Search Nearby", type="primary", use_container_width=True)
        with col_btn2:
            if st.button("🗑️ Clear Results", use_container_width=True):
                st.session_state.search_results = None
                st.rerun()
        
        if search_clicked:
            params = {
                'lat': lat,
                'lon': lon,
                'radius_km': radius,
                'limit': limit
            }
            
            if status != "All":
                params['status'] = status
            if connector:
                params['connector_type'] = connector
            
            with st.spinner("Searching..."):
                data, error = api_call("GET", "/chargers/nearby", params=params)
            
            if error:
                st.session_state.search_results = None
                st.error(f"❌ {error}")
            elif data:
                results = data.get('nearest_chargers', [])
                if results:
                    st.session_state.search_results = {
                        'results': results,
                        'lat': lat,
                        'lon': lon
                    }
                else:
                    st.session_state.search_results = None
                    st.warning("No chargers found in this area")
        
        # Display results from session state
        if st.session_state.search_results:
            results = st.session_state.search_results['results']
            lat = st.session_state.search_results['lat']
            lon = st.session_state.search_results['lon']
            
            st.success(f"✅ Found {len(results)} chargers")
            
            # Show map
            m = create_map(results, center_lat=lat, center_lon=lon, zoom=10)
            st_folium(m, width=None, height=400)
            
            # Show results
            st.markdown("### Results")
            for charger in results:
                with st.expander(f"{charger['name']} - {charger['distance_km']} km"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**City:** {charger['city']}")
                        st.write(f"**Connector:** {charger['connector_type']}")
                        st.write(f"**Status:** {charger.get('status', 'unknown').title()}")
                    with col2:
                        st.write(f"**Distance:** {charger['distance_km']} km")
                        st.write(f"**Duration:** ~{charger['duration_minutes']} min")
                        if charger.get('avg_rating'):
                            st.write(f"**Rating:** ⭐ {charger['avg_rating']}")
                    
                    # Add to favorites button with clear feedback
                    if st.session_state.token:
                        col_btn1, col_btn2 = st.columns([1, 3])
                        with col_btn1:
                            if st.button("⭐ Favorite", key=f"fav_{charger['id']}", use_container_width=True):
                                data, err = api_call("POST", f"/favorites/{charger['id']}")
                                if err:
                                    if "already in favorites" in str(err).lower():
                                        st.info("Already in favorites!")
                                    else:
                                        st.error(f"Error: {err}")
                                else:
                                    st.success("✅ Added to favorites!")
                                    st.balloons()
                                    # Force a small delay to ensure DB commit
                                    import time
                                    time.sleep(0.5)
                    else:
                        st.info("💡 Login to add favorites")
    
    else:  # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            city = st.text_input("City", placeholder="e.g., Tunis")
        with col2:
            usage_type = st.selectbox("Usage Type", ["All", "Public", "Private"])
        with col3:
            connector_type = st.text_input("Connector", placeholder="e.g., Type 2")
        
        col1, col2 = st.columns(2)
        with col1:
            status = st.selectbox("Status", ["All", "working", "broken", "occupied", "under_construction", "unknown"], key="filter_status")
        with col2:
            min_rating = st.slider("Min Rating", 0.0, 5.0, 0.0, 0.5)
        
        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            search_clicked = st.button("🔍 Search", type="primary", use_container_width=True)
        with col_btn2:
            if st.button("🗑️ Clear Results", key="clear_filter", use_container_width=True):
                st.session_state.filter_results = None
                st.rerun()
        
        if search_clicked:
            params = {'limit': 100}
            
            if city:
                params['city'] = city
            if usage_type != "All":
                params['usage_type'] = usage_type
            if connector_type:
                params['connector_type'] = connector_type
            if status != "All":
                params['status'] = status
            if min_rating > 0:
                params['min_rating'] = min_rating
            
            with st.spinner("Searching..."):
                data, error = api_call("GET", "/chargers/search", params=params)
            
            if error:
                st.session_state.filter_results = None
                st.error(f"❌ {error}")
            elif data:
                results = data.get('results', [])
                if results:
                    st.session_state.filter_results = results
                else:
                    st.session_state.filter_results = None
                    st.warning("No chargers found with these filters")
        
        # Display results from session state
        if st.session_state.filter_results:
            results = st.session_state.filter_results
            st.success(f"✅ Found {len(results)} chargers")
            
            for charger in results:
                with st.expander(f"{charger['name']} - {charger['city']}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Connector:** {charger['connector_type']}")
                        st.write(f"**Usage:** {charger['usage_type']}")
                    with col2:
                        st.write(f"**Status:** {charger.get('status', 'unknown').replace('_', ' ').title()}")
                        if charger.get('avg_rating'):
                            st.write(f"**Rating:** ⭐ {charger['avg_rating']}")
                    
                    # Add to favorites button
                    if st.session_state.token:
                        col_btn1, col_btn2 = st.columns([1, 3])
                        with col_btn1:
                            if st.button("⭐ Favorite", key=f"fav_filter_{charger['id']}", use_container_width=True):
                                data, err = api_call("POST", f"/favorites/{charger['id']}")
                                if err:
                                    if "already in favorites" in str(err).lower():
                                        st.info("Already in favorites!")
                                    else:
                                        st.error(f"Error: {err}")
                                else:
                                    st.success("✅ Added to favorites!")
                                    st.balloons()
                                    # Force a small delay to ensure DB commit
                                    import time
                                    time.sleep(0.5)
                    else:
                        st.info("💡 Login to add favorites")

# ============= LOGIN =============
elif page == "🔐 Login":
    st.markdown("## 🔐 Login")
    
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    
    if st.button("Login", type="primary"):
        if not email or not password:
            st.error("Please fill in all fields")
        else:
            data, error = api_call("POST", "/auth/login", data={"username": email, "password": password})
            if error:
                st.error(f"Login failed: {error}")
            elif data:
                st.session_state.token = data['access_token']
                st.session_state.user_email = email
                st.success("✅ Login successful!")
                st.rerun()

# ============= REGISTER =============
elif page == "📝 Register":
    st.markdown("## 📝 Register")
    
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    confirm = st.text_input("Confirm Password", type="password")
    
    st.info("Password must be 8+ characters with uppercase, lowercase, and numbers")
    
    if st.button("Register", type="primary"):
        if not email or not password or not confirm:
            st.error("Please fill in all fields")
        elif password != confirm:
            st.error("Passwords don't match")
        else:
            data, error = api_call("POST", "/auth/register", json={"email": email, "password": password})
            if error:
                st.error(f"Registration failed: {error}")
            else:
                st.success("✅ Registration successful! Please login.")

# ============= FAVORITES =============
elif page == "⭐ Favorites":
    if not st.session_state.token:
        st.warning("Please login to view favorites")
    else:
        st.markdown("## ⭐ My Favorites")
        st.info("💡 Tip: Add chargers to favorites from the 'Find Chargers' page by clicking the ⭐ Favorite button")
        
        with st.spinner("Loading favorites..."):
            data, error = api_call("GET", "/favorites")
        
        if error:
            st.error(f"Error loading favorites: {error}")
        elif data is not None:
            if len(data) == 0:
                st.warning("📭 No favorites yet! Go to 'Find Chargers' to add some.")
            else:
                st.success(f"✅ {len(data)} favorite charger(s)")
                
                m = create_map(data)
                st_folium(m, width=None, height=400)
                
                for charger in data:
                    with st.expander(f"{charger['name']} - {charger['city']}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Connector:** {charger['connector_type']}")
                            st.write(f"**Status:** {charger.get('status', 'unknown').replace('_', ' ').title()}")
                        with col2:
                            if charger.get('avg_rating'):
                                st.write(f"**Rating:** ⭐ {charger['avg_rating']}")
                        
                        if st.button("❌ Remove from Favorites", key=f"remove_{charger['id']}", type="secondary"):
                            _, err = api_call("DELETE", f"/favorites/{charger['id']}")
                            if not err:
                                st.success("✅ Removed from favorites!")
                                st.rerun()
                            else:
                                st.error(f"Error: {err}")

# ============= VEHICLE =============
elif page == "🚗 My Vehicle":
    if not st.session_state.token:
        st.warning("Please login to manage vehicle")
    else:
        st.markdown("## 🚗 My Vehicle")
        
        # Get current vehicle
        data, error = api_call("GET", "/users/me/vehicle")
        if data:
            st.info(f"Current: {data['connector_type']} | Range: {data['range_km']} km")
        
        st.markdown("---")
        
        connector = st.selectbox("Connector Type", ["Type 2", "CCS", "CHAdeMO", "Type 1", "Tesla"])
        range_km = st.number_input("Range (km)", min_value=50.0, max_value=1000.0, value=200.0, step=10.0)
        
        if st.button("Save Vehicle", type="primary"):
            _, error = api_call("POST", "/users/me/vehicle", json={"connector_type": connector, "range_km": range_km})
            if error:
                st.error(f"Error: {error}")
            else:
                st.success("✅ Vehicle saved!")
                st.rerun()

# ============= TRIP PLANNING =============
elif page == "🛣️ Plan Trip":
    if not st.session_state.token:
        st.warning("Please login to plan trips")
    else:
        st.markdown("## 🛣️ Plan Trip")
        
        # Check vehicle
        vehicle_data, error = api_call("GET", "/users/me/vehicle")
        if not vehicle_data:
            st.warning("⚠️ Please add your vehicle first!")
        else:
            st.info(f"🚗 Vehicle: {vehicle_data['connector_type']} | Range: {vehicle_data['range_km']} km")
            
            st.markdown("---")
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("### 📍 Start")
                start_lat = st.number_input("Start Latitude", value=36.8, format="%.6f", key="start_lat")
                start_lon = st.number_input("Start Longitude", value=10.1, format="%.6f", key="start_lon")
            
            with col2:
                st.markdown("### 🎯 End")
                end_lat = st.number_input("End Latitude", value=36.9, format="%.6f", key="end_lat")
                end_lon = st.number_input("End Longitude", value=10.2, format="%.6f", key="end_lon")
            
            if st.button("🗺️ Plan Trip", type="primary"):
                data, error = api_call("POST", "/trips/plan", json={
                    "start_lat": start_lat,
                    "start_lon": start_lon,
                    "end_lat": end_lat,
                    "end_lon": end_lon
                })
                
                if error:
                    st.error(f"Error: {error}")
                elif data:
                    st.success("✅ Trip planned!")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Distance", f"{data['total_distance_km']} km")
                    with col2:
                        st.metric("Duration", f"{data['estimated_duration_minutes']} min")
                    
                    # Check if charging needed
                    vehicle_range = vehicle_data['range_km']
                    trip_distance = data['total_distance_km']
                    
                    if trip_distance > vehicle_range:
                        st.warning(f"⚠️ Trip distance ({trip_distance} km) exceeds vehicle range ({vehicle_range} km)")
                        st.info("You will need to charge during this trip. Find chargers along your route.")
                    else:
                        st.success(f"✅ Your vehicle can make this trip without charging!")
                    
                    waypoints = json.loads(data.get('waypoints', '[]'))
                    if waypoints:
                        st.markdown("### ⚡ Suggested Charging Stops")
                        for i, wp in enumerate(waypoints, 1):
                            st.write(f"**Stop {i}:** {wp['name']}")

# ============= STATISTICS =============
elif page == "📊 Statistics":
    if not st.session_state.token:
        st.warning("Please login to view statistics")
    else:
        st.markdown("## 📊 My Statistics")
        
        data, error = api_call("GET", "/users/me/stats")
        if error:
            st.error(f"Error: {error}")
        elif data:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Trips", data['total_trips'])
            with col2:
                st.metric("Reviews", data['total_reviews'])
            with col3:
                st.metric("Favorites", data['total_favorites'])
            with col4:
                st.metric("Reports", data['total_reports'])
            
            st.markdown("---")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Distance", f"{data['total_distance_km']} km")
            with col2:
                st.metric("CO₂ Saved", f"{data['co2_saved_kg']} kg")

# ============= WRITE REVIEW =============
elif page == "📝 Write Review":
    if not st.session_state.token:
        st.warning("Please login to write reviews")
    else:
        st.markdown("## 📝 Write a Review")
        
        data, error = api_call("GET", "/chargers?limit=100")
        if error:
            st.error(f"Error: {error}")
        elif data and data.get('results'):
            chargers = data['results']
            
            selected_idx = st.selectbox(
                "Select Charger",
                range(len(chargers)),
                format_func=lambda i: f"{chargers[i]['name']} - {chargers[i]['city']}"
            )
            
            rating = st.slider("Rating", 1, 5, 5)
            comment = st.text_area("Comment (optional)", max_chars=500)
            
            if st.button("Submit Review", type="primary"):
                charger_id = chargers[selected_idx]['id']
                _, error = api_call("POST", f"/chargers/{charger_id}/reviews", json={
                    "rating": rating,
                    "comment": comment if comment else None
                })
                
                if error:
                    st.error(f"Error: {error}")
                else:
                    st.success("✅ Review submitted!")

# ============= REPORT CHARGER =============
elif page == "🚨 Report Charger":
    if not st.session_state.token:
        st.warning("Please login to report chargers")
    else:
        st.markdown("## 🚨 Report Charger Status")
        
        data, error = api_call("GET", "/chargers?limit=100")
        if error:
            st.error(f"Error: {error}")
        elif data and data.get('results'):
            chargers = data['results']
            
            selected_idx = st.selectbox(
                "Select Charger",
                range(len(chargers)),
                format_func=lambda i: f"{chargers[i]['name']} - {chargers[i]['city']}"
            )
            
            issue_type = st.selectbox("Status", ["working", "broken", "occupied", "under_construction"])
            description = st.text_area("Description", max_chars=500, placeholder="Describe what you observed...")
            
            if st.button("Submit Report", type="primary"):
                if not description:
                    st.error("Please provide a description")
                else:
                    charger_id = chargers[selected_idx]['id']
                    _, error = api_call("POST", f"/chargers/{charger_id}/report", json={
                        "issue_type": issue_type,
                        "description": description
                    })
                    
                    if error:
                        st.error(f"Error: {error}")
                    else:
                        st.success("✅ Report submitted! Thank you for helping the community.")

# ============= FOOTER =============
st.markdown("---")
st.markdown('<p style="text-align: center; color: #888;">⚡ EV Charging Tunisia v3.0</p>', unsafe_allow_html=True)
