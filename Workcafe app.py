import json
from pathlib import Path
from typing import Dict, List, Any, Union

import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium


CUSTOM_CAFES_FILE = Path(__file__).with_name("custom_cafes.csv")
REVIEWS_FILE = Path(__file__).with_name("user_reviews.json")
VISITS_FILE = Path(__file__).with_name("visited_cafes.json")


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


def load_visits() -> Dict[str, bool]:
    if not VISITS_FILE.exists():
        return {}
    try:
        return json.loads(VISITS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_visits(visits: Dict[str, bool]) -> None:
    VISITS_FILE.write_text(json.dumps(visits, indent=2), encoding="utf-8")


def average_metric(entries: List[Dict[str, Any]], key: str) -> float:
    values = [entry.get(key, 0) for entry in entries]
    return round(average(values), 1)


def compute_workability_score(metrics: Dict[str, float]) -> float:
    quiet_score = 6 - metrics["noise"]
    weighted = (
        metrics["wifi"] * 0.30
        + metrics["outlets"] * 0.25
        + quiet_score * 0.20
        + metrics["seating"] * 0.15
        + metrics["laptop_friendliness"] * 0.10
    )
    return round(weighted, 1)


def get_tier(score: float) -> str:
    if score < 2:
        return "Avoid"
    elif score < 3:
        return "Risky"
    elif score < 4:
        return "Solid"
    elif score < 5:
        return "Strong"
    else:
        return "Elite"


def get_marker_color(score: Union[float, None], is_selected: bool) -> str:
    if is_selected:
        return "blue"
    if score is None:
        return "gray"

    rounded = round(score)
    if rounded <= 1:
        return "red"
    elif rounded == 2:
        return "orange"
    elif rounded == 3:
        return "beige"
    elif rounded == 4:
        return "lightgreen"
    else:
        return "green"


def get_left_box_class(score: Union[float, None], is_selected: bool) -> str:
    if is_selected:
        return "selected-entry"

    if score is None:
        return "score-unreviewed"

    if score < 2:
        return "score-bad"
    elif score < 4:
        return "score-okay"
    else:
        return "score-good"


def get_user_metrics(user_entries: List[Dict[str, Any]]) -> Union[Dict[str, float], None]:
    if not user_entries:
        return None

    return {
        "wifi": average_metric(user_entries, "wifi"),
        "outlets": average_metric(user_entries, "outlets"),
        "noise": average_metric(user_entries, "noise"),
        "seating": average_metric(user_entries, "seating"),
        "laptop_friendliness": average_metric(user_entries, "laptop_friendliness"),
        "chill": average_metric(user_entries, "chill"),
    }


@st.cache_data(show_spinner=False)
def load_custom_cafes() -> List[Dict[str, Any]]:
    if not CUSTOM_CAFES_FILE.exists():
        return []

    df = pd.read_csv(CUSTOM_CAFES_FILE)
    required_cols = {"id", "name", "address", "lat", "lon"}
    if not required_cols.issubset(df.columns):
        return []

    cafes: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        name = str(row["name"]).strip()
        address = str(row["address"]).strip()

        if not name or not address:
            continue

        try:
            lat = float(row["lat"])
            lon = float(row["lon"])
        except Exception:
            continue

        neighborhood = (
            str(row["neighborhood"]).strip()
            if "neighborhood" in df.columns and pd.notna(row["neighborhood"])
            else "Fairfield Area"
        )

        phone = ""
        if "phone" in df.columns and pd.notna(row["phone"]):
            phone = str(row["phone"]).strip()
            if phone.lower() == "nan":
                phone = ""

        cafes.append({
            "id": f"custom_{row['id']}",
            "name": name,
            "address": address,
            "neighborhood": neighborhood,
            "lat": lat,
            "lon": lon,
            "phone": phone,
        })

    return cafes


def merge_reviews_into_cafes(
    cafes: List[Dict[str, Any]],
    reviews: Dict[str, List[Dict[str, Any]]],
    visits: Dict[str, bool],
) -> List[Dict[str, Any]]:
    enriched = []

    for cafe in cafes:
        user_entries = reviews.get(str(cafe["id"]), [])
        metrics = get_user_metrics(user_entries)
        visited = bool(visits.get(str(cafe["id"]), False))

        workability = compute_workability_score(metrics) if metrics else None
        tier = get_tier(workability) if workability is not None else "Unreviewed"
        vibe = "Chill" if metrics and metrics["chill"] >= 4.2 else "Work"

        chips = [
            "Visited" if visited else "Not visited",
            f'{len(user_entries)} review{"s" if len(user_entries) != 1 else ""}',
        ]

        place = {
            **cafe,
            "visited": visited,
            "userReviewCount": len(user_entries),
            "userNotes": user_entries,
            "workability": workability,
            "tier": tier,
            "vibe": vibe,
            "chips": chips,
        }

        if metrics:
            place.update(metrics)
        else:
            place.update({
                "wifi": None,
                "outlets": None,
                "noise": None,
                "seating": None,
                "laptop_friendliness": None,
                "chill": None,
            })

        enriched.append(place)

    reviewed = [p for p in enriched if p["workability"] is not None]
    unreviewed = [p for p in enriched if p["workability"] is None]

    reviewed.sort(key=lambda x: x["workability"], reverse=True)
    unreviewed.sort(key=lambda x: x["name"].lower())

    return reviewed + unreviewed


def init_defaults() -> None:
    st.session_state.setdefault("selected_id", None)
    st.session_state.setdefault("map_bounds", None)


def metric_text(value: Union[float, None]) -> str:
    return "—" if value is None else f"{value}/5"


def render_metric_pill(label: str, value: Union[float, None], bg: str = "#f3f4f6") -> str:
    return f"""
    <div style="
        background:{bg};
        border:1px solid rgba(15,23,42,0.08);
        border-radius:999px;
        padding:8px 12px;
        font-size:14px;
        font-weight:600;
        color:#0f172a;
        display:inline-block;
        margin:4px 6px 0 0;
    ">
        {label}: {metric_text(value)}
    </div>
    """


def in_bounds(place: Dict[str, Any], bounds: Dict[str, Any]) -> bool:
    if not bounds:
        return True
    try:
        south = bounds["_southWest"]["lat"]
        west = bounds["_southWest"]["lng"]
        north = bounds["_northEast"]["lat"]
        east = bounds["_northEast"]["lng"]
    except Exception:
        return True

    return south <= place["lat"] <= north and west <= place["lon"] <= east


def main() -> None:
    st.set_page_config(page_title="Workcafe Fairfield", page_icon="☕", layout="wide")
    init_defaults()

    st.markdown("""
    <style>
    :root {
        --bg: #f8fafc;
        --panel: #ffffff;
        --text: #0f172a;
        --muted: #64748b;
        --border: #e2e8f0;
        --accent: #4f46e5;
        --accent2: #6366f1;
        --save1: #0ea5e9;
        --save2: #38bdf8;
    }

    html, body, [class*="css"] {
        color: var(--text) !important;
    }

    .stApp {
        background:
            radial-gradient(circle at top left, rgba(99,102,241,0.10), transparent 35%),
            radial-gradient(circle at top right, rgba(16,185,129,0.08), transparent 25%),
            linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
    }

    .block-container {
        padding-top: 1.35rem;
        padding-bottom: 2rem;
        max-width: 1450px;
    }

    [data-testid="stSidebar"] {
        background: rgba(255,255,255,0.92);
        border-right: 1px solid var(--border);
    }

    [data-testid="stElementToolbar"],
    [data-testid="stToolbar"] {
        display: none !important;
    }

    .hero {
        background: linear-gradient(135deg, #111827 0%, #1f2937 100%);
        color: white !important;
        border-radius: 24px;
        padding: 24px 28px;
        margin-bottom: 16px;
        box-shadow: 0 18px 50px rgba(15,23,42,0.18);
    }

    .hero h1 {
        margin: 0;
        font-size: 2.15rem;
        color: white !important;
    }

    .hero p {
        margin: 8px 0 0 0;
        color: rgba(255,255,255,0.88) !important;
        font-size: 1rem;
    }

    .section-card {
        background: rgba(255,255,255,0.90);
        backdrop-filter: blur(10px);
        border: 1px solid var(--border);
        border-radius: 22px;
        padding: 18px;
        box-shadow: 0 10px 30px rgba(15,23,42,0.06);
        color: var(--text) !important;
    }

    .selected-score {
        background: linear-gradient(135deg, var(--accent) 0%, var(--accent2) 100%);
        color: white !important;
        border-radius: 18px;
        padding: 18px 20px;
        margin-bottom: 14px;
        box-shadow: 0 10px 24px rgba(79,70,229,0.28);
    }

    .selected-score-label,
    .selected-score-value,
    .selected-score-sub {
        color: white !important;
    }

    .selected-score-label {
        font-size: 0.9rem;
        opacity: 0.92;
        margin-bottom: 4px;
    }

    .selected-score-value {
        font-size: 2rem;
        font-weight: 800;
        line-height: 1;
    }

    .selected-score-sub {
        margin-top: 6px;
        font-size: 0.95rem;
        opacity: 0.96;
    }

    .review-note {
        background: #f8fafc;
        border-left: 4px solid var(--accent);
        padding: 12px 14px;
        border-radius: 12px;
        margin-bottom: 10px;
        color: #334155 !important;
    }

    .quick-scroll {
        max-height: 78vh;
        overflow-y: auto;
        padding-right: 4px;
    }

    .quick-scroll::-webkit-scrollbar {
        width: 8px;
    }

    .quick-scroll::-webkit-scrollbar-thumb {
        background: #cbd5e1;
        border-radius: 999px;
    }

    .quick-scroll::-webkit-scrollbar-track {
        background: transparent;
    }

    .stButton > button {
        width: 100%;
        border-radius: 16px;
        border: 1px solid var(--border);
        color: #0f172a !important;
        font-weight: 700;
        padding: 1rem 1rem;
        box-shadow: 0 8px 18px rgba(15,23,42,0.05);
        text-align: left;
        white-space: pre-wrap;
        line-height: 1.35;
        margin-bottom: 10px;
    }

    .score-unreviewed button {
        background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%) !important;
    }

    .score-bad button {
        background: linear-gradient(180deg, #fee2e2 0%, #fff1f2 100%) !important;
        border-color: #fca5a5 !important;
        color: #7f1d1d !important;
    }

    .score-okay button {
        background: linear-gradient(180deg, #fef3c7 0%, #fffbeb 100%) !important;
        border-color: #fcd34d !important;
        color: #78350f !important;
    }

    .score-good button {
        background: linear-gradient(180deg, #dcfce7 0%, #f0fdf4 100%) !important;
        border-color: #86efac !important;
        color: #14532d !important;
    }

    .selected-entry button {
        background: linear-gradient(180deg, #dbeafe 0%, #eff6ff 100%) !important;
        border-color: #60a5fa !important;
        box-shadow: 0 10px 24px rgba(59,130,246,0.18) !important;
        color: #1e3a8a !important;
    }

    .stButton > button:hover {
        filter: brightness(0.99);
    }

    div[data-testid="stFormSubmitButton"] > button {
        background: linear-gradient(135deg, var(--save1) 0%, var(--save2) 100%) !important;
        color: white !important;
        border: none !important;
        text-align: center !important;
        box-shadow: 0 8px 18px rgba(14,165,233,0.22) !important;
    }

    .stTextInput > div > div,
    .stTextArea > div > div,
    .stTextArea textarea,
    .stDateInput > div > div,
    .stSelectbox > div > div,
    div[data-baseweb="select"] > div,
    div[data-baseweb="base-input"] > div,
    div[data-baseweb="input"] > div {
        border-radius: 14px !important;
        color: var(--text) !important;
        background: #ffffff !important;
        background-color: #ffffff !important;
    }

    .stTextInput input,
    .stTextArea textarea,
    .stDateInput input,
    .stSelectbox div[data-baseweb="select"] *,
    .stRadio *,
    .stMarkdown,
    .stCaption,
    label,
    p,
    span,
    div {
        color: var(--text) !important;
    }

    input, textarea, select {
        background: #ffffff !important;
        color: #0f172a !important;
    }

    [data-baseweb="select"] {
        background: #ffffff !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="hero">
        <h1>☕ Workcafe Fairfield</h1>
        <p>Browse cafes in Fairfield, track which places you’ve visited, and score cafes with your own reviews.</p>
    </div>
    """, unsafe_allow_html=True)

    reviews = load_reviews()
    visits = load_visits()
    cafes = load_custom_cafes()
    places = merge_reviews_into_cafes(cafes, reviews, visits)

    if cafes:
        st.success(f"Loaded {len(cafes)} cafes from your custom dataset.")
    else:
        st.error("Could not load custom_cafes.csv or it is empty.")

    search = st.text_input("Search all cafes", placeholder="Search by cafe name or address")
    mode = st.radio(
        "Show",
        ["All", "Visited", "Not Visited", "Reviewed", "Unreviewed", "Work", "Chill"],
        index=0,
        horizontal=True,
    )
    sort_by = st.selectbox("Sort by", ["Best score", "Most reviews", "Alphabetical"], index=0)

    filtered_places = []
    query = search.lower().strip()

    for place in places:
        haystack = " ".join([
            place["name"],
            place["neighborhood"],
            place["address"],
            place["phone"],
            " ".join(place["chips"]),
        ]).lower()

        matches_search = query in haystack if query else True

        if mode == "Visited":
            matches_mode = place["visited"]
        elif mode == "Not Visited":
            matches_mode = not place["visited"]
        elif mode == "Reviewed":
            matches_mode = place["userReviewCount"] > 0
        elif mode == "Unreviewed":
            matches_mode = place["userReviewCount"] == 0
        elif mode == "Work":
            matches_mode = place["userReviewCount"] > 0 and place["vibe"] == "Work"
        elif mode == "Chill":
            matches_mode = place["userReviewCount"] > 0 and place["vibe"] == "Chill"
        else:
            matches_mode = True

        if matches_search and matches_mode:
            filtered_places.append(place)

    if sort_by == "Best score":
        filtered_places.sort(
            key=lambda x: (x["workability"] is not None, x["workability"] or -1),
            reverse=True
        )
    elif sort_by == "Most reviews":
        filtered_places.sort(key=lambda x: x["userReviewCount"], reverse=True)
    else:
        filtered_places.sort(key=lambda x: x["name"].lower())

    place_by_id = {str(p["id"]): p for p in filtered_places}
    place_by_name = {p["name"]: p for p in filtered_places}

    if filtered_places and (
        st.session_state["selected_id"] is None
        or str(st.session_state["selected_id"]) not in place_by_id
    ):
        st.session_state["selected_id"] = filtered_places[0]["id"]

    selected_place = place_by_id.get(str(st.session_state["selected_id"])) if filtered_places else None

    left, middle, right = st.columns([0.95, 1.35, 1.0], gap="large")

    with middle:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Live Map")

        center = [41.14, -73.26]
        if selected_place:
            center = [selected_place["lat"], selected_place["lon"]]
        elif filtered_places:
            center = [filtered_places[0]["lat"], filtered_places[0]["lon"]]

        m = folium.Map(location=center, zoom_start=13, tiles="CartoDB Positron", control_scale=True)

        for place in filtered_places:
            popup_phone = f'<div style="color:#334155; margin-top:4px;">{place["phone"]}</div>' if place["phone"] else ""
            is_selected = selected_place is not None and str(place["id"]) == str(selected_place["id"])
            marker_color = get_marker_color(place["workability"], is_selected)

            popup_html = f"""
            <div style="width:240px; color:#0f172a;">
                <h4 style="margin-bottom:6px; color:#0f172a;">{place["name"]}</h4>
                <div style="color:#334155;">{place["neighborhood"]}</div>
                <div style="color:#334155; margin-top:4px;">{place["address"]}</div>
                {popup_phone}
                <div style="margin-top:8px; color:#334155;">
                    <strong>Score:</strong> {place["workability"] if place["workability"] is not None else "Unreviewed"}
                </div>
                <div style="color:#334155;"><strong>Status:</strong> {"Visited" if place["visited"] else "Not visited"}</div>
                <div style="color:#334155;"><strong>Reviews:</strong> {place["userReviewCount"]}</div>
            </div>
            """
            folium.Marker(
                location=[place["lat"], place["lon"]],
                popup=folium.Popup(popup_html, max_width=260),
                tooltip=place["name"],
                icon=folium.Icon(color=marker_color, icon="coffee", prefix="fa"),
            ).add_to(m)

        map_data = st_folium(m, width=None, height=520)

        clicked_name = None
        if isinstance(map_data, dict):
            clicked_name = map_data.get("last_object_clicked_tooltip")
            bounds = map_data.get("bounds")
            if bounds:
                st.session_state["map_bounds"] = bounds

        if clicked_name and clicked_name in place_by_name:
            clicked_place = place_by_name[clicked_name]
            if str(clicked_place["id"]) != str(st.session_state["selected_id"]):
                st.session_state["selected_id"] = clicked_place["id"]
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    selected_place = place_by_id.get(str(st.session_state["selected_id"])) if filtered_places else None
    current_bounds = st.session_state.get("map_bounds")

    visible_places = [p for p in filtered_places if in_bounds(p, current_bounds)]
    if not visible_places:
        visible_places = filtered_places[:]

    if selected_place is not None and any(str(p["id"]) == str(selected_place["id"]) for p in visible_places):
        visible_places = [p for p in visible_places if str(p["id"]) != str(selected_place["id"])]
        visible_places.insert(0, selected_place)

    with left:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Quick Browse")
        st.caption(f"{len(visible_places)} cafes in current map view")

        if not visible_places:
            st.info("No cafes visible in the current map area.")
        else:
            st.markdown('<div class="quick-scroll">', unsafe_allow_html=True)

            for place in visible_places:
                score_text = (
                    f'{place["workability"]}/5 • {place["tier"]}'
                    if place["workability"] is not None
                    else "Unreviewed"
                )
                visited_text = "Visited" if place["visited"] else "Not visited"

                entry_parts = [place["name"], place["address"]]
                if place["phone"]:
                    entry_parts.append(place["phone"])
                entry_parts.append(f"{score_text} • {visited_text}")
                entry_label = "\n".join(entry_parts)

                is_selected = (
                    selected_place is not None
                    and str(place["id"]) == str(selected_place["id"])
                )
                wrapper_class = get_left_box_class(place["workability"], is_selected)

                st.markdown(f'<div class="{wrapper_class}">', unsafe_allow_html=True)
                if st.button(
                    entry_label,
                    key=f"quick_{place['id']}",
                    use_container_width=True
                ):
                    st.session_state["selected_id"] = place["id"]
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)

        if selected_place:
            score_big = (
                f'{selected_place["workability"]}/5'
                if selected_place["workability"] is not None
                else "Unreviewed"
            )
            score_sub = selected_place["tier"] if selected_place["workability"] is not None else "No reviews yet"

            st.markdown(f"### {selected_place['name']}")
            st.caption(f"{selected_place['neighborhood']} • {selected_place['address']}")
            if selected_place["phone"]:
                st.caption(selected_place["phone"])

            current_visit = bool(visits.get(str(selected_place["id"]), False))
            visited_now = st.checkbox("Visited", value=current_visit, key=f"visited_{selected_place['id']}")
            if visited_now != current_visit:
                visits[str(selected_place["id"])] = visited_now
                save_visits(visits)
                st.rerun()

            st.markdown(f"""
            <div class="selected-score">
                <div class="selected-score-label">Workability Score</div>
                <div class="selected-score-value">{score_big}</div>
                <div class="selected-score-sub">{score_sub}</div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown(
                render_metric_pill("WiFi", selected_place["wifi"], "#e0f2fe")
                + render_metric_pill("Outlets", selected_place["outlets"], "#ede9fe")
                + render_metric_pill("Noise", selected_place["noise"], "#fee2e2")
                + render_metric_pill("Seating", selected_place["seating"], "#dcfce7")
                + render_metric_pill("Laptop-Friendly", selected_place["laptop_friendliness"], "#fef3c7")
                + render_metric_pill("Chill", selected_place["chill"], "#f3e8ff"),
                unsafe_allow_html=True
            )

            st.markdown("#### Reviews")
            if selected_place["userNotes"]:
                for note in selected_place["userNotes"][:5]:
                    note_text = note.get("notes", "").strip() or "No written note."
                    reviewer_name = note.get("reviewer_name", "Anonymous")
                    review_date = note.get("review_date", "Unknown")
                    st.markdown(f"""
                    <div class="review-note">
                        <strong>{reviewer_name}</strong> / Date: {review_date}<br>
                        WiFi {note.get("wifi", "—")}/5 •
                        Outlets {note.get("outlets", "—")}/5 •
                        Noise {note.get("noise", "—")}/5 •
                        Seating {note.get("seating", "—")}/5 •
                        Laptop {note.get("laptop_friendliness", "—")}/5 •
                        Chill {note.get("chill", "—")}/5
                        <div style="margin-top:8px;">{note_text}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No reviews yet.")

            st.markdown("#### Add review")
            with st.form(key="review_form", clear_on_submit=True):
                reviewer_name = st.text_input("Your name", placeholder="Ex: Jack")
                review_date = st.date_input("Review date")
                wifi = st.slider("WiFi", 1, 5, value=4)
                outlets = st.slider("Outlets", 1, 5, value=4)
                noise = st.slider("Noise", 1, 5, value=3)
                seating = st.slider("Seating", 1, 5, value=4)
                laptop_friendliness = st.slider("Laptop Friendliness", 1, 5, value=4)
                chill = st.slider("Chill factor", 1, 5, value=4)
                notes = st.text_area(
                    "Notes",
                    height=120,
                    placeholder="Ex: Great before 10am, solid seating, weak outlets near the back."
                )

                submitted = st.form_submit_button("Save review", use_container_width=True)

                if submitted:
                    visits[str(selected_place["id"])] = True
                    save_visits(visits)

                    entry = {
                        "reviewer_name": reviewer_name.strip() or "Anonymous",
                        "review_date": review_date.strftime("%m/%d/%y"),
                        "wifi": wifi,
                        "outlets": outlets,
                        "noise": noise,
                        "seating": seating,
                        "laptop_friendliness": laptop_friendliness,
                        "chill": chill,
                        "notes": notes.strip(),
                    }

                    key = str(selected_place["id"])
                    reviews.setdefault(key, [])
                    reviews[key] = [entry] + reviews[key]
                    reviews[key] = reviews[key][:50]

                    save_reviews(reviews)
                    st.cache_data.clear()
                    st.success("Review saved.")
                    st.rerun()
        else:
            st.info("Select a cafe from Quick Browse or the map.")

        st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()