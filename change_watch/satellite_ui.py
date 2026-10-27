"""Map selection, calendar dates and transparent imagery-quality controls."""

import json
from datetime import datetime, timedelta, timezone

import folium
import streamlit as st
from branca.element import MacroElement, Template
from folium.plugins import Draw
from shapely.geometry import box, shape
from streamlit_folium import st_folium

from .satellite import (
    EARLIEST_DATE,
    NoClearPair,
    QualityPolicy,
    SatelliteError,
    SatelliteRequest,
    find_pair,
    make_grid,
    normalize_aoi,
)


class SingleRegion(MacroElement):
    """A newly drawn crop replaces the preceding one in the editable group."""

    _template = Template("""
    {% macro script(this, kwargs) %}
    {{ this._parent.get_name() }}.on('draw:created', function(e) {
        {{ this.group.get_name() }}.eachLayer(function(layer) {
            if (layer !== e.layer) { {{ this.group.get_name() }}.removeLayer(layer); }
        });
    });
    {% endmacro %}
    """)

    def __init__(self, group):
        super().__init__()
        self._name = "SingleRegion"
        self.group = group


def draw_map(aoi=None):
    center = st.session_state.get("satellite_center", (53.28, 69.4))
    canvas = folium.Map(location=center, zoom_start=11, tiles=None, control_scale=True)
    # This map has no Bootstrap popups, jQuery handlers or icon-font markers.
    # Load just Leaflet plus Draw's own assets to keep map startup lightweight.
    canvas.default_js = [("leaflet", "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js")]
    canvas.default_css = [
        ("leaflet_css", "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css")
    ]
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, Maxar, Earthstar Geographics and the GIS User Community",
        name="Satellite basemap",
        max_zoom=19,
    ).add_to(canvas)
    folium.TileLayer("OpenStreetMap", name="Street map", show=False).add_to(canvas)
    group = folium.FeatureGroup(name="Your region", control=False).add_to(canvas)
    if aoi:
        polygon = shape(aoi)
        locations = [(lat, lon) for lon, lat in polygon.exterior.coords]
        holes = [[(lat, lon) for lon, lat in ring.coords] for ring in polygon.interiors]
        folium.Polygon(
            [locations, *holes] if holes else locations,
            color="#D8F171",
            weight=3,
            fill_opacity=0.12,
        ).add_to(group)
        west, south, east, north = polygon.bounds
        canvas.fit_bounds([[south, west], [north, east]], padding=(30, 30))
    Draw(
        feature_group=group,
        show_geometry_on_click=False,
        draw_options={
            "polyline": False,
            "circle": False,
            "circlemarker": False,
            "marker": False,
            "rectangle": {"shapeOptions": {"color": "#D8F171"}},
            "polygon": {"allowIntersection": False, "shapeOptions": {"color": "#D8F171"}},
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(canvas)
    SingleRegion(group).add_to(canvas)
    folium.LayerControl(collapsed=True).add_to(canvas)
    return st_folium(
        canvas,
        key=f"satellite_map_{st.session_state.get('satellite_map_epoch', 0)}",
        height=480,
        use_container_width=True,
        returned_objects=["all_drawings"],
        wrap_longitude=True,
    )


def reset_map_view(aoi=None):
    """Remount only for deliberate navigation, reset, or re-entering map mode.

    st_folium includes its script in the component key. Feeding each drawing
    back into the script remounts the component on the next edit, losing that
    edit's response. Keep a fixed initial seed while Leaflet owns the drawings.
    """
    st.session_state["satellite_map_seed"] = aoi
    st.session_state["satellite_map_epoch"] = st.session_state.get("satellite_map_epoch", 0) + 1


def clear_selection():
    st.session_state.pop("satellite_aoi", None)
    st.session_state.pop("satellite_pair", None)
    st.session_state.pop("satellite_diagnostics", None)
    reset_map_view()


def region_picker():
    with st.expander("Move the map or enter exact bounds"):
        with st.form("map_location"):
            left, right = st.columns(2)
            lat = left.number_input("Map latitude", -80.0, 84.0, 53.28, format="%.5f")
            lon = right.number_input("Map longitude", -180.0, 180.0, 69.4, format="%.5f")
            if st.form_submit_button("Move map"):
                clear_selection()
                st.session_state["satellite_center"] = (lat, lon)
        st.caption("Exact bounds also work when map tiles are unavailable. Coordinates use WGS84.")
        with st.form("map_bounds"):
            left, right = st.columns(2)
            west = left.number_input("West longitude", -180.0, 180.0, 69.25, format="%.5f")
            east = right.number_input("East longitude", -180.0, 180.0, 69.27, format="%.5f")
            south = left.number_input("South latitude", -80.0, 84.0, 53.2, format="%.5f")
            north = right.number_input("North latitude", -80.0, 84.0, 53.22, format="%.5f")
            if st.form_submit_button("Use these bounds"):
                if west >= east or south >= north:
                    st.error("West must be less than east, and south less than north.")
                else:
                    try:
                        candidate = normalize_aoi(box(west, south, east, north).__geo_interface__)
                        clear_selection()
                        st.session_state["satellite_aoi"] = candidate
                        st.session_state["satellite_map_seed"] = candidate
                    except SatelliteError as error:
                        st.error(str(error))
    drawing = draw_map(st.session_state.get("satellite_map_seed"))
    # None is the component's initial response. [] is an explicit deletion.
    drawings = drawing.get("all_drawings") if drawing else None
    if drawings is not None:
        if not drawings:
            st.session_state.pop("satellite_aoi", None)
        else:
            try:
                st.session_state["satellite_aoi"] = normalize_aoi(drawings[-1])
            except SatelliteError as error:
                st.session_state.pop("satellite_aoi", None)
                st.error(str(error))
    if st.button("Clear region", key="satellite_clear"):
        clear_selection()
        st.rerun()
    return st.session_state.get("satellite_aoi")


def render_satellite_source():
    st.subheader("1 · Draw your region")
    st.caption(
        "Use the rectangle or polygon tool on the left. Draw again to replace the crop; use the edit tool to adjust its edges."
    )
    aoi = region_picker()
    st.caption(
        "The basemap helps locate the site. Its imagery is independent of the dates chosen below."
    )

    st.subheader("2 · Choose the comparison dates")
    today = datetime.now(timezone.utc).date()
    left, right, window_column = st.columns([1, 1, 1])
    start = left.date_input(
        "Start date",
        value=today - timedelta(days=365),
        min_value=EARLIEST_DATE,
        max_value=today,
        key="satellite_start",
    )
    end = right.date_input(
        "End date",
        value=today - timedelta(days=7),
        min_value=EARLIEST_DATE,
        max_value=today,
        key="satellite_end",
    )
    window = window_column.selectbox(
        "Search near each endpoint",
        [0, 3, 7, 14, 30],
        index=3,
        format_func=lambda days: "Exact dates only" if not days else f"Up to {days} days inward",
        key="satellite_window",
    )
    st.caption(
        "Search forward from start and backward from end, always inside your chosen interval. The nearest pair that passes the quality checks is used; actual capture dates are shown below."
    )

    st.subheader("3 · Keep the region clear")
    strict = st.checkbox(
        "Require the whole region to pass cloud and coverage checks",
        value=True,
        key="satellite_strict",
        help="Reject every detected cloud, cirrus, shadow, snow, unclassified or missing-data pixel in the region. This is based on Sentinel-2's 20 m scene classification.",
    )
    with st.expander("Cloud and download settings", expanded=not strict):
        scene_cloud = st.slider(
            "Maximum cloud cover across the whole scene (%)",
            0,
            100,
            20,
            key="satellite_scene_cloud",
        )
        st.caption(
            "This is a coarse filter. Each candidate is also checked inside your exact polygon."
        )
        if strict:
            aoi_cloud, min_usable = 0.0, 100.0
            st.write("Region limit: 0% detected cloud/shadow · 100% usable coverage.")
        else:
            aoi_cloud = float(
                st.slider(
                    "Maximum buffered cloud/shadow inside the region (%)",
                    0,
                    20,
                    1,
                    key="satellite_aoi_cloud",
                )
            )
            min_usable = float(
                st.slider(
                    "Minimum usable coverage on both dates (%)",
                    50,
                    100,
                    95,
                    key="satellite_min_usable",
                )
            )
            st.caption(
                "Unsuitable pixels remain excluded from detection even when you allow partial coverage."
            )
        buffer_m = st.select_slider(
            "Extra buffer around detected clouds and shadows (m)",
            options=[0, 20, 40, 60, 100, 200],
            value=60,
            key="satellite_buffer",
        )
        resolution = st.selectbox(
            "Comparison pixel size",
            [10, 20],
            format_func=lambda value: f"{value} metres",
            key="satellite_resolution",
        )
    st.caption(
        "Cloud screening uses Sentinel-2 scene classification. Small clouds, haze and classification errors can be missed, so inspect the selected pair."
    )
    if not aoi:
        st.info("Draw a region on the map, then choose your dates to find a clear image pair.")
        st.stop()
    try:
        request = SatelliteRequest(
            aoi,
            start,
            end,
            window,
            resolution,
            QualityPolicy(float(scene_cloud), aoi_cloud, min_usable, buffer_m),
        )
        grid = make_grid(aoi, resolution)
    except SatelliteError as error:
        st.error(str(error))
        st.stop()
    west, south, east, north = shape(aoi).bounds
    st.caption(
        f"Selected: {grid.area_km2:.2f} km² · {grid.width:,} × {grid.height:,} pixels · [{west:.5f}, {south:.5f}, {east:.5f}, {north:.5f}]"
    )
    st.download_button(
        "Save selected region (GeoJSON)",
        json.dumps({"type": "Feature", "properties": {}, "geometry": aoi}, indent=2),
        "aoi.geojson",
        "application/geo+json",
        key="satellite_download_aoi",
    )
    if st.button("Find clear imagery & compare", type="primary", key="satellite_fetch"):
        st.session_state.pop("satellite_pair", None)
        st.session_state.pop("satellite_diagnostics", None)
        with st.status("Searching and checking your region…", expanded=True) as status:
            try:
                pair = find_pair(request, progress=status.write)
                st.session_state["satellite_pair"] = (request.key, pair)
                status.update(label="Clear image pair ready", state="complete", expanded=False)
            except SatelliteError as error:
                status.update(label="No comparison loaded", state="error", expanded=False)
                st.session_state["satellite_diagnostics"] = (
                    request.key,
                    str(error),
                    error.diagnostics if isinstance(error, NoClearPair) else [],
                )
    failure = st.session_state.get("satellite_diagnostics")
    if failure and failure[0] == request.key:
        st.error(failure[1])
        if failure[2]:
            with st.expander("See why scenes were rejected", expanded=True):
                st.dataframe(failure[2], hide_index=True, width="stretch")
    stored = st.session_state.get("satellite_pair")
    if not stored or stored[0] != request.key:
        if stored:
            st.info(
                "Region, dates or quality settings changed. Find imagery again for this selection."
            )
        st.stop()
    pair = stored[1]
    st.success(
        f"Comparing {pair.metadata['before_date']} → {pair.metadata['after_date']} · {pair.provenance['joint_usable_percent']:.2f}% of the region usable on both dates"
    )
    st.markdown("**Selected observations**")
    st.dataframe(
        [
            {
                "Image": label,
                "Captured (UTC)": crop.scene["properties"]["datetime"],
                "Scene cloud (%)": crop.scene["properties"]["eo:cloud_cover"],
                "Region cloud/shadow (%)": crop.quality["cloud_shadow_percent"],
                "Region usable (%)": crop.quality["usable_percent"],
                "Scene ID": crop.scene["id"],
            }
            for label, crop in (("Before", pair.before), ("After", pair.after))
        ],
        hide_index=True,
        width="stretch",
    )
    with st.expander("Acquisition details and scene checks"):
        st.json(pair.provenance)
        st.dataframe(pair.diagnostics, hide_index=True, width="stretch")
    st.caption(
        "Contains modified Copernicus Sentinel data · Earth Search by Element 84 · Both images use the same UTM grid and fixed reflectance display scale."
    )
    return pair
