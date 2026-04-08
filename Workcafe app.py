import streamlit as st
 
st.title("Workcafe")
 
 
import json
import math
from pathlib import Path
from typing import Dict, List, Any, Union, Tuple

import requests
import streamlit as st
import folium
from streamlit_folium import st_folium

NYC_BBOX = {
    "south": 40.49,
    "west": -74.28,
    "north": 40.92,
    "east": -73.68,
}

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]

BOROUGH_PRESETS = {
    "All": NYC_BBOX,
    "Manhattan": {"south": 40.68, "west": -74.03, "north": 40.88, "east": -73.90},
    "Brooklyn": {"south": 40.57, "west": -74.05, "north": 40.74, "east": -73.83},
    "Queens": {"south": 40.54, "west": -73.96, "north": 40.81, "east": -73.70},
    "Bronx": {"south": 40.79, "west": -73.93, "north": 40.92, "east": -73.77},
}

FALLBACK_PLACES = [
    {
        "id": 900001,
        "type": "node",
        "lat": 40.7307,
        "lon": -73.9973,
        "tags": {
            "name": "Think Coffee",
            "amenity": "cafe",
            "addr:street": "Mercer St",
            "internet_access": "yes",
            "opening_hours": "Mo-Su 07:00-19:00",
            "outdoor_seating": "yes",
        },
    },
    {
        "id": 900002,
        "type": "node",
        "lat": 40.7411,
        "lon": -73.9897,
        "tags": {
            "name": "Gregorys Coffee",
            "amenity": "cafe",
            "addr:street": "5th Ave",
            "internet_access": "yes",
            "opening_hours": "Mo-Su 06:30-18:00",
        },
    },
    {
        "id": 900003,
        "type": "node",
        "lat": 40.7295,
        "lon": -73.9995,
        "tags": {
            "name": "Joe Coffee Company",
            "amenity": "cafe",
            "addr:street": "Waverly Pl",
            "internet_access": "customers",
            "outdoor_seating": "yes",
        },
    },
    {
        "id": 900004,
        "type": "node",
        "lat": 40.7238,
        "lon": -73.9946,
        "tags": {
            "name": "La Colombe Coffee Roasters",
            "amenity": "cafe",
            "addr:street": "Lafayette St",
            "internet_access": "yes",
            "opening_hours": "Mo-Su 07:00-18:00",
        },
    },
    {
        "id": 900005,
        "type": "node",
        "lat": 40.7422,
        "lon": -74.0062,
        "tags": {
            "name": "Starbucks Reserve",
            "amenity": "cafe",
            "addr:street": "W 15th St",
            "internet_access": "yes",
            "opening_hours": "Mo-Su 07:00-22:00",
        },
    },
    {
        "id": 900006,
        "type": "node",
        "lat": 40.7174,
        "lon": -73.9582,
        "tags": {
            "name": "Devoción",
            "amenity": "cafe",
            "addr:street": "Wythe Ave",
            "outdoor_seating": "yes",
            "opening_hours": "Mo-Su 08:00-18:00",
        },
    },
]

REVIEWS_FILE = Path(__file__).with_name("user_reviews.json")


def clamp(value: float, min_value: float = 1.0, max_value: float = 5.0) -> float:
    return min(max_value, max(min_value, value))


def average(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(float(v or 0) for v in values) / len(values)


def load_reviews() -> Dict[str, List[Dict[str, Any]]]:
    if not REVIEWS_FILE.exists():
        return {}
    try:
        return json.loads(REVIEWS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_reviews(reviews: Dict[str, List[Dict[str, Any]]]) -> None:
    REVIEWS_FILE.write_text(json.dumps(reviews, indent=2), encoding="utf-8")


def get_base_scores_from_tags(tags: Dict[str, Any]) -> Dict[str, float]:
    amenity = tags.get("amenity", "place")
    internet_access = str(tags.get("internet_access", "")).lower()
    has_wifi = internet_access in {"yes", "wlan", "free", "customers", "terminal"}
    has_outdoor = str(tags.get("outdoor_seating", "")).lower() == "yes"
    opening_hours = bool(tags.get("opening_hours"))

    wifi = 4.4 if has_wifi else 3.2
    outlets = 3.0
    noise = 3.0
    seating = 3.6
    tolerance = 3.4
    chill = 3.8

    if amenity == "cafe":
        wifi += 0.3
        seating += 0.2
        tolerance += 0.3
        chill += 0.2

    if amenity == "restaurant":
        noise += 0.4
        outlets -= 0.4
        tolerance -= 0.5
        chill += 0.1

    if amenity == "fast_food":
        noise += 0.8
        outlets -= 0.8
        seating -= 0.4
        tolerance -= 0.7

    if has_outdoor:
        chill += 0.5
        seating += 0.2

    if opening_hours:
        tolerance += 0.1

    return {
        "wifi": round(clamp(wifi), 1),
        "outlets": round(clamp(outlets), 1),
        "noise": round(clamp(noise), 1),
        "seating": round(clamp(seating), 1),
        "tolerance": round(clamp(tolerance), 1),
        "chill": round(clamp(chill), 1),
    }


def blend_metrics(base: Dict[str, float], user_entries: List[Dict[str, Any]]) -> Dict[str, float]:
    if not user_entries:
        return base

    user_metrics = {
        "wifi": average([entry.get("wifi", 0) for entry in user_entries]),
        "outlets": average([entry.get("outlets", 0) for entry in user_entries]),
        "noise": average([entry.get("noise", 0) for entry in user_entries]),
        "seating": average([entry.get("seating", 0) for entry in user_entries]),
        "tolerance": average([entry.get("tolerance", 0) for entry in user_entries]),
        "chill": average([entry.get("chill", 0) for entry in user_entries]),
    }

    return {
        key: round(base[key] * 0.45 + user_metrics[key] * 0.55, 1)
        for key in ["wifi", "outlets", "noise", "seating", "tolerance", "chill"]
    }


def compute_workability_score(metrics: Dict[str, float]) -> float:
    quiet_score = 6 - metrics["noise"]
    weighted = (
        metrics["wifi"] * 0.30
        + metrics["outlets"] * 0.25
        + quiet_score * 0.20
        + metrics["seating"] * 0.15
        + metrics["tolerance"] * 0.10
    )
    return round(weighted, 1)


def get_tier(score: float) -> str:
    if score >= 4.6:
        return "Elite"
    if score >= 4.2:
        return "Strong"
    if score >= 3.7:
        return "Solid"
    if score >= 3.1:
        return "Risky"
    return "Avoid"


def get_marker_color(score: float) -> str:
    if score >= 4.6:
        return "green"
    if score >= 4.2:
        return "lightgreen"
    if score >= 3.7:
        return "orange"
    if score >= 3.1:
        return "red"
    return "darkred"


def normalize_place(item: Dict[str, Any], borough: str, reviews: Dict[str, List[Dict[str, Any]]]) -> Union[Dict[str, Any], None]:
    lat = item.get("lat") or item.get("center", {}).get("lat")
    lon = item.get("lon") or item.get("center", {}).get("lon")
    tags = item.get("tags", {})
    name = tags.get("name")

    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not name:
        return None

    user_entries = reviews.get(str(item["id"]), [])
    base = get_base_scores_from_tags(tags)
    metrics = blend_metrics(base, user_entries)
    category = {
        "cafe": "Cafe",
        "restaurant": "Restaurant",
        "fast_food": "Fast Food",
    }.get(tags.get("amenity", ""), "Place")
    workability = compute_workability_score(metrics)

    chips = []
    if tags.get("internet_access"):
        chips.append(f'WiFi: {tags["internet_access"]}')
    if str(tags.get("outdoor_seating", "")).lower() == "yes":
        chips.append("Outdoor seating")
    if tags.get("opening_hours"):
        chips.append("Hours listed")
    chips.append(f'{len(user_entries)} user review{"s" if len(user_entries) != 1 else ""}' if user_entries else "Needs reviews")

    return {
        "id": item["id"],
        "name": name,
        "category": category,
        "neighborhood": tags.get("addr:suburb") or tags.get("addr:neighbourhood") or borough,
        "address": " ".join([x for x in [tags.get("addr:housenumber"), tags.get("addr:street")] if x]) or "Address not listed",
        "lat": lat,
        "lon": lon,
        "tags": tags,
        "userReviewCount": len(user_entries),
        "userNotes": user_entries,
        "workability": workability,
        "tier": get_tier(workability),
        "vibe": "Chill" if metrics["chill"] >= 4.2 else "Work",
        "chips": chips,
        **metrics,
    }


def fetch_overpass_with_fallback(query: str) -> Tuple[List[Dict[str, Any]], str]:
    last_error = None
    for endpoint in OVERPASS_URLS:
        try:
            response = requests.post(
                endpoint,
                data=query.encode("utf-8"),
                headers={"Content-Type": "text/plain;charset=UTF-8"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            elements = data.get("elements", [])
            if elements:
                return elements, "live"
            raise RuntimeError("No live place data returned.")
        except Exception as exc:
            last_error = exc

    return FALLBACK_PLACES, f"fallback ({last_error})"


@st.cache_data(show_spinner=False)
def load_places_for_borough(borough: str, reviews_snapshot: str) -> Tuple[List[Dict[str, Any]], str]:
    bbox = BOROUGH_PRESETS[borough]
    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"~"cafe|restaurant|fast_food"]({bbox["south"]},{bbox["west"]},{bbox["north"]},{bbox["east"]});
      way["amenity"~"cafe|restaurant|fast_food"]({bbox["south"]},{bbox["west"]},{bbox["north"]},{bbox["east"]});
    );
    out center tags;
    """
    reviews = json.loads(reviews_snapshot)
    elements, source = fetch_overpass_with_fallback(query)
    items = [
        normalize_place(item, borough, reviews)
        for item in elements
    ]
    items = [item for item in items if item]
    items.sort(key=lambda x: x["workability"], reverse=True)
    return items[:60], source


def reset_form() -> None:
    st.session_state["wifi"] = 4.0
    st.session_state["outlets"] = 4.0
    st.session_state["noise"] = 3.0
    st.session_state["seating"] = 4.0
    st.session_state["tolerance"] = 4.0
    st.session_state["chill"] = 4.0
    st.session_state["notes"] = ""


def main() -> None:
    st.set_page_config(page_title="Workable NYC", page_icon="☕", layout="wide")
    st.title("☕ Workable NYC")
    st.caption("Find NYC spots where you can actually work and chill.")

    # Custom CSS for a stellar look
    st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    .css-1d391kg {
        background-color: rgba(255, 255, 255, 0.9);
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .stButton>button {
        background-color: #4CAF50;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 10px 20px;
        font-size: 16px;
    }
    .stButton>button:hover {
        background-color: #45a049;
    }
    .stSlider {
        padding: 10px 0;
    }
    .metric-card {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 15px;
        margin: 5px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

    if "selected_id" not in st.session_state:
        st.session_state["selected_id"] = None
    if "wifi" not in st.session_state:
        reset_form()

    reviews = load_reviews()

    with st.sidebar:
        st.header("Search and filter")
        search = st.text_input("Search by place, neighborhood, or tag")
        borough = st.radio("Borough", list(BOROUGH_PRESETS.keys()), index=1)
        mode = st.radio("Mode", ["All", "Work", "Chill"], index=0)

    places, source = load_places_for_borough(borough, json.dumps(reviews, sort_keys=True))

    if source.startswith("live"):
        st.success("Loaded live NYC venue data.")
    else:
        st.warning("Live feed was unavailable, so a built-in NYC sample dataset is being shown instead.")

    filtered_places = []
    query = search.lower().strip()
    for place in places:
        haystack = " ".join([
            place["name"],
            place["category"],
            place["neighborhood"],
            place["address"],
            " ".join(place["chips"]),
        ]).lower()
        matches_search = query in haystack
        matches_mode = (mode == "All") or (place["vibe"] == mode)
        if matches_search and matches_mode:
            filtered_places.append(place)

    if filtered_places and st.session_state["selected_id"] not in [p["id"] for p in filtered_places]:
        st.session_state["selected_id"] = filtered_places[0]["id"]

    selected_place = next((p for p in filtered_places if p["id"] == st.session_state["selected_id"]), None)
    if selected_place is None and filtered_places:
        selected_place = filtered_places[0]
        st.session_state["selected_id"] = selected_place["id"]

    avg_workability = round(average([p["workability"] for p in filtered_places]), 1) if filtered_places else 0
    avg_wifi = round(average([p["wifi"] for p in filtered_places]), 1) if filtered_places else 0
    avg_outlets = round(average([p["outlets"] for p in filtered_places]), 1) if filtered_places else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <h3>Avg Workability</h3>
            <h2>{avg_workability}/5</h2>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <h3>Avg WiFi</h3>
            <h2>{avg_wifi}/5</h2>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <h3>Avg Outlets</h3>
            <h2>{avg_outlets}/5</h2>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <h3>Visible Places</h3>
            <h2>{len(filtered_places)}</h2>
        </div>
        """, unsafe_allow_html=True)

    left, middle, right = st.columns([1.0, 1.25, 0.95], gap="large")

    with left:
        st.subheader("Top NYC places")
        if not filtered_places:
            st.info("No places match this search.")
        else:
            for place in filtered_places:
                label = f'{place["name"]} — {place["workability"]}/5 ({place["tier"]})'
                if st.button(label, key=f'pick_{place["id"]}', use_container_width=True):
                    st.session_state["selected_id"] = place["id"]
                    st.rerun()

    with middle:
        st.subheader("Live map preview")
        center = [40.75, -73.98]
        if selected_place:
            center = [selected_place["lat"], selected_place["lon"]]

        m = folium.Map(location=center, zoom_start=13, tiles="OpenStreetMap", control_scale=True)

        for place in filtered_places:
            popup_html = f"""
            <div style="width:220px;">
                <h4 style="margin-bottom:6px;">{place["name"]}</h4>
                <div><strong>{place["category"]}</strong></div>
                <div>{place["neighborhood"]}</div>
                <div style="margin-top:6px;"><strong>Workability:</strong> {place["workability"]}/5</div>
                <div><strong>WiFi:</strong> {place["wifi"]}/5</div>
                <div><strong>Outlets:</strong> {place["outlets"]}/5</div>
                <div><strong>Noise:</strong> {place["noise"]}/5</div>
                <div style="margin-top:6px;">{", ".join(place["chips"])}</div>
            </div>
            """
            folium.Marker(
                location=[place["lat"], place["lon"]],
                popup=folium.Popup(popup_html, max_width=260),
                tooltip=f'{place["name"]} • {place["workability"]}/5',
                icon=folium.Icon(color=get_marker_color(place["workability"]), icon="coffee", prefix="fa"),
            ).add_to(m)

        st_folium(m, width=None, height=500)

        if selected_place:
            st.markdown(f"""
            <div style="background-color: #ffffff; border-radius: 10px; padding: 20px; margin-top: 20px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">
                <h3 style="color: #333; margin-bottom: 10px;">📍 {selected_place["name"]}</h3>
                <p><strong>Address:</strong> {selected_place["address"]}</p>
                <p><strong>Category:</strong> {selected_place["category"]}</p>
                <p><strong>Neighborhood:</strong> {selected_place["neighborhood"]}</p>
                <p><strong>Workability Score:</strong> {selected_place["workability"]}/5 ({selected_place["tier"]})</p>
                <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px;">
                    <span style="background: #e8f5e8; padding: 5px 10px; border-radius: 5px;">WiFi: {selected_place["wifi"]}/5</span>
                    <span style="background: #fff3e0; padding: 5px 10px; border-radius: 5px;">Outlets: {selected_place["outlets"]}/5</span>
                    <span style="background: #fce4ec; padding: 5px 10px; border-radius: 5px;">Noise: {selected_place["noise"]}/5</span>
                    <span style="background: #f3e5f5; padding: 5px 10px; border-radius: 5px;">Seating: {selected_place["seating"]}/5</span>
                    <span style="background: #e0f2f1; padding: 5px 10px; border-radius: 5px;">Tolerance: {selected_place["tolerance"]}/5</span>
                    <span style="background: #fff8e1; padding: 5px 10px; border-radius: 5px;">Chill: {selected_place["chill"]}/5</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if selected_place["userNotes"]:
                st.markdown("**Recent user notes**")
                for note in selected_place["userNotes"][:3]:
                    st.info(note.get("notes") or "No written note added.")

    with right:
        st.subheader("✍️ Add your review")
        if selected_place:
            st.write(f'**Reviewing: {selected_place["name"]}**')
            with st.form(key="review_form"):
                st.slider("WiFi", 1.0, 5.0, key="wifi", step=0.1)
                st.slider("Outlets", 1.0, 5.0, key="outlets", step=0.1)
                st.slider("Noise", 1.0, 5.0, key="noise", step=0.1)
                st.slider("Seating", 1.0, 5.0, key="seating", step=0.1)
                st.slider("Stay tolerance", 1.0, 5.0, key="tolerance", step=0.1)
                st.slider("Chill factor", 1.0, 5.0, key="chill", step=0.1)
                st.text_area("Notes", key="notes", height=120, placeholder="Share your experience... e.g., Good before 10am, but almost no outlets...")

                submitted = st.form_submit_button("Save review", use_container_width=True)
                if submitted:
                    entry = {
                        "wifi": st.session_state["wifi"],
                        "outlets": st.session_state["outlets"],
                        "noise": st.session_state["noise"],
                        "seating": st.session_state["seating"],
                        "tolerance": st.session_state["tolerance"],
                        "chill": st.session_state["chill"],
                        "notes": st.session_state["notes"].strip(),
                    }
                    key = str(selected_place["id"])
                    reviews.setdefault(key, [])
                    reviews[key] = [entry] + reviews[key]
                    reviews[key] = reviews[key][:12]
                    save_reviews(reviews)
                    load_places_for_borough.clear()
                    reset_form()
                    st.success("Review saved! 🎉")
                    st.rerun()
        else:
            st.write("Select a place from the list to review it.")


if __name__ == "__main__":
    main()
