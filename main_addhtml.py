import streamlit as st
import streamlit.components.v1 as components
import json
import base64
import io
import math
from PIL import Image
import pandas as pd
from datetime import datetime

# -----------------------------------------------------------------------------
# 1. SETUP PAGE & STATE
# -----------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="RenovateRight - Shape Editor")

if "app_stage" not in st.session_state:
    st.session_state.app_stage = "onboarding"  # 'onboarding' -> 'calibrate' -> 'workspace'

if "project_data" not in st.session_state:
    st.session_state.project_data = {}

if "temp_image_b64" not in st.session_state:
    st.session_state.temp_image_b64 = None

if "temp_image" not in st.session_state:
    st.session_state.temp_image = None


# -----------------------------------------------------------------------------
# SCREEN 1: ONBOARDING SCREEN
# -----------------------------------------------------------------------------
def show_onboarding_screen():
    st.title("🏠 RenovateRight: Floor Plan Setup")
    st.write("Start a new renovation project with an image, or resume an existing project file.")
    st.markdown("---")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown("### Start a New Project")
        plan_name = st.text_input("Project Name", "My Renovation")
        uploaded_img = st.file_uploader("Upload Floor Plan Image", type=["png", "jpg", "jpeg"])

        if uploaded_img is not None:
            image = Image.open(uploaded_img)
            st.session_state.temp_image = image
            
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            img_b64 = base64.b64encode(buffered.getvalue()).decode()
            st.session_state.temp_image_b64 = f"data:image/png;base64,{img_b64}"

            st.image(image, caption="Uploaded Preview", use_container_width=True)

        if st.button("Proceed to Scale Calibration ➔", type="primary", use_container_width=True):
            if uploaded_img is None:
                st.warning("Please upload an image first.")
            else:
                st.session_state.project_data = {
                    "plan_name": plan_name,
                    "furniture": [],
                    "walls": [],
                    "doors": [],
                    "scale_cm_per_px": 1.0,
                }
                # Clear out any old data from query params
                st.query_params.clear()
                st.session_state.app_stage = "calibrate"
                st.rerun()

    with col2:
        st.markdown("### Resume a Past Project")
        uploaded_json = st.file_uploader("Upload Saved Project (.json)", type=["json"])
        if uploaded_json is not None:
            try:
                data = json.load(uploaded_json)
                st.success(f"Project '{data.get('plan_name', 'Saved Plan')}' ready to open.")
                if st.button("Open Project Workspace ➔", use_container_width=True):
                    st.session_state.project_data = data
                    
                    # Pre-load URL parameters from the saved file
                    raw_vecs = data.get("raw_vectors", [])
                    st.query_params["raw_elements"] = json.dumps(raw_vecs)
                    
                    st.session_state.app_stage = "workspace"
                    st.rerun()
            except Exception as e:
                st.error(f"Invalid JSON file: {e}")


# -----------------------------------------------------------------------------
# SCREEN 2: PRECISION SCALE CALIBRATION
# -----------------------------------------------------------------------------
def show_calibration_screen():
    st.title("📏 Calibrate Scale (Drag Lines & Handles)")
    st.markdown("""
    * Drag the **handles** of the **Blue Line** to set a known **horizontal** width.
    * Drag the **handles** of the **Green Line** to set a known **vertical** length.
    * Drag the middle of a line to move it across your blueprint.
    """)

    image = st.session_state.temp_image
    img_b64 = st.session_state.temp_image_b64
    if image is None or img_b64 is None:
        st.session_state.app_stage = "onboarding"
        st.rerun()

    max_w = 800
    display_w = min(max_w, image.width)
    display_h = int(image.height * (display_w / image.width))

    # Restore previous calibration values or use defaults
    pd = st.session_state.project_data
    blue_line_start = pd.get("calib_blue_line", {"x1": display_w * 0.2, "y1": display_h * 0.25, "x2": display_w * 0.8})
    green_line_start = pd.get("calib_green_line", {"x1": display_w * 0.15, "y1": display_h * 0.2, "y2": display_h * 0.8})
    
    blue_px = abs(blue_line_start['x2'] - blue_line_start['x1'])
    green_px = abs(green_line_start['y2'] - green_line_start['y1'])

    # Get current values from query params if they exist, otherwise use stored/default
    try:
        current_blue_px = float(st.query_params.get("b_px", blue_px))
        current_green_px = float(st.query_params.get("g_px", green_px))
    except (ValueError, TypeError):
        current_blue_px = blue_px
        current_green_px = green_px

    col_canvas, col_inputs = st.columns([0.65, 0.35], gap="large")

    with col_canvas:
        html_code = f"""
        <div style="font-family: sans-serif;">
            <canvas id="calib_canvas" width="{display_w}" height="{display_h}" 
                    style="border:2px solid #888; border-radius:8px; user-select:none; cursor:crosshair;"></canvas>
            <p style="font-size:12px; color:#555; margin-top:6px;">
                💡 <b>Controls:</b> Drag handles to resize length | Drag line bodies to reposition on wall.
            </p>
        </div>
        <script>
            const canvas = document.getElementById('calib_canvas');
            const ctx = canvas.getContext('2d');
            const bgImg = new Image();
            bgImg.src = "{img_b64}";

            let blueLine = {{ x1: {blue_line_start['x1']}, y1: {blue_line_start['y1']}, x2: {blue_line_start['x2']}, y2: {blue_line_start['y1']} }};
            let greenLine = {{ x1: {green_line_start['x1']}, y1: {green_line_start['y1']}, x2: {green_line_start['x1']}, y2: {green_line_start['y2']} }};
            let dragging = null;
            let dragOffset = 0;

            function syncWithStreamlit() {{
                const bLen = Math.abs(blueLine.x2 - blueLine.x1);
                const gLen = Math.abs(greenLine.y2 - greenLine.y1);
                const url = new URL(window.parent.location.href);
                url.searchParams.set("b_px", bLen.toFixed(1));
                url.searchParams.set("g_px", gLen.toFixed(1));
                // Also save the line positions themselves for restoring later
                url.searchParams.set("b_line", JSON.stringify({{x1: blueLine.x1, y1: blueLine.y1, x2: blueLine.x2}}));
                url.searchParams.set("g_line", JSON.stringify({{x1: greenLine.x1, y1: greenLine.y1, y2: greenLine.y2}}));
                window.parent.history.replaceState(null, '', url.toString());
            }}

            function draw() {{
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(bgImg, 0, 0, canvas.width, canvas.height);
                
                const lineWidth = 2; 
                const handleRadius = 6;

                ctx.strokeStyle = '#0066FF'; ctx.lineWidth = lineWidth;
                ctx.beginPath(); ctx.moveTo(blueLine.x1, blueLine.y1); ctx.lineTo(blueLine.x2, blueLine.y1); ctx.stroke();
                
                ctx.strokeStyle = '#00AA00'; ctx.lineWidth = lineWidth;
                ctx.beginPath(); ctx.moveTo(greenLine.x1, greenLine.y1); ctx.lineTo(greenLine.x1, greenLine.y2); ctx.stroke();
                
                ctx.fillStyle = '#0066FF';
                ctx.beginPath(); ctx.arc(blueLine.x1, blueLine.y1, handleRadius, 0, 2 * Math.PI); ctx.fill();
                ctx.beginPath(); ctx.arc(blueLine.x2, blueLine.y1, handleRadius, 0, 2 * Math.PI); ctx.fill();
                
                ctx.fillStyle = '#00AA00';
                ctx.beginPath(); ctx.arc(greenLine.x1, greenLine.y1, handleRadius, 0, 2 * Math.PI); ctx.fill();
                ctx.beginPath(); ctx.arc(greenLine.x1, greenLine.y2, handleRadius, 0, 2 * Math.PI); ctx.fill();
            }}

            bgImg.onload = () => {{ draw(); syncWithStreamlit(); }};

            function getMousePos(e) {{ const rect = canvas.getBoundingClientRect(); return {{ x: e.clientX - rect.left, y: e.clientY - rect.top }}; }}

            canvas.onmousedown = (e) => {{
                const pos = getMousePos(e);
                const handleHitRadius = 12;
                const bodyHitDistance = 10;

                if (Math.hypot(pos.x - blueLine.x1, pos.y - blueLine.y1) < handleHitRadius) {{ dragging = {{ type: 'blue_handle', point: 'p1' }}; return; }}
                if (Math.hypot(pos.x - blueLine.x2, pos.y - blueLine.y1) < handleHitRadius) {{ dragging = {{ type: 'blue_handle', point: 'p2' }}; return; }}
                if (Math.hypot(pos.x - greenLine.x1, pos.y - greenLine.y1) < handleHitRadius) {{ dragging = {{ type: 'green_handle', point: 'p1' }}; return; }}
                if (Math.hypot(pos.x - greenLine.x1, pos.y - greenLine.y2) < handleHitRadius) {{ dragging = {{ type: 'green_handle', point: 'p2' }}; return; }}
                
                if (Math.abs(pos.y - blueLine.y1) < bodyHitDistance && pos.x > Math.min(blueLine.x1, blueLine.x2) && pos.x < Math.max(blueLine.x1, blueLine.x2)) {{
                    dragging = {{ type: 'blue_body' }}; dragOffset = pos.y - blueLine.y1; return;
                }}
                if (Math.abs(pos.x - greenLine.x1) < bodyHitDistance && pos.y > Math.min(greenLine.y1, greenLine.y2) && pos.y < Math.max(greenLine.y1, greenLine.y2)) {{
                    dragging = {{ type: 'green_body' }}; dragOffset = pos.x - greenLine.x1; return;
                }}
            }};

            canvas.onmousemove = (e) => {{
                const pos = getMousePos(e);
                if (!dragging) return;
                if (dragging.type === 'blue_handle') {{ if (dragging.point === 'p1') blueLine.x1 = pos.x; else blueLine.x2 = pos.x; }}
                else if (dragging.type === 'blue_body') {{ const newY = pos.y - dragOffset; blueLine.y1 = newY; blueLine.y2 = newY; }}
                else if (dragging.type === 'green_handle') {{ if (dragging.point === 'p1') greenLine.y1 = pos.y; else greenLine.y2 = pos.y; }}
                else if (dragging.type === 'green_body') {{ const newX = pos.x - dragOffset; greenLine.x1 = newX; greenLine.x2 = newX; }}
                draw();
            }};

            function stopDragging() {{ if (dragging) {{ dragging = null; syncWithStreamlit(); }} }}
            canvas.onmouseup = stopDragging;
            canvas.onmouseleave = stopDragging;
        </script>
        """
        components.html(html_code, height=display_h + 40)

    with col_inputs:
        st.subheader("Wall Dimensions")
        
        st.markdown("##### 🔵 Horizontal Wall")
        h_real_cm = st.number_input("Real Width (cm)", min_value=10, max_value=3000, value=pd.get("calib_h_cm", 400), step=10)
        
        st.markdown("---")
        st.markdown("##### 🟢 Vertical Wall")
        v_real_cm = st.number_input("Real Length (cm)", min_value=10, max_value=3000, value=pd.get("calib_v_cm", 500), step=10)

        st.markdown("---")
        b1, b2 = st.columns(2)
        if b1.button("↩️ Back to Workspace", use_container_width=True):
            st.session_state.app_stage = "workspace"
            st.rerun()

        if b2.button("Confirm Scale & Enter Workspace ➔", type="primary", use_container_width=True):
            scale_x = h_real_cm / max(1.0, current_blue_px)
            scale_y = v_real_cm / max(1.0, current_green_px)
            avg_scale = (scale_x + scale_y) / 2.0
            
            # Store image and scale info
            st.session_state.project_data["image_width_px"] = image.width
            st.session_state.project_data["image_height_px"] = image.height
            st.session_state.project_data["scale_cm_per_px"] = avg_scale
            
            # Store calibration settings for next time
            st.session_state.project_data["calib_h_cm"] = h_real_cm
            st.session_state.project_data["calib_v_cm"] = v_real_cm
            try:
                st.session_state.project_data["calib_blue_line"] = json.loads(st.query_params.get("b_line"))
                st.session_state.project_data["calib_green_line"] = json.loads(st.query_params.get("g_line"))
            except: # If JSON is invalid or missing, don't store
                pass

            st.session_state.app_stage = "workspace"
            st.rerun()


# -----------------------------------------------------------------------------
# SCREEN 3: SHAPE EDITOR WORKSPACE
# -----------------------------------------------------------------------------
def show_workspace():
    data = st.session_state.project_data
    image = st.session_state.temp_image
    img_b64 = st.session_state.temp_image_b64

    # --- Correctly calculate the scale for JavaScript (pixels per meter) ---
    scale_cm_per_px = data.get("scale_cm_per_px", 1.0)
    if scale_cm_per_px == 0: scale_cm_per_px = 1.0 # Avoid division by zero
    js_scale_px_per_m = 100.0 / scale_cm_per_px

    # Get original image dimensions from project data
    img_px_w = data.get("image_width_px", 100)
    img_px_h = data.get("image_height_px", 100)

    # Fetch geometry lists from query params safely. This is our state persistence.
    try:
        raw_elements_string = st.query_params.get("raw_elements", "[]")
        drawn_elements = json.loads(raw_elements_string)
    except Exception:
        drawn_elements = []

    # Safe wall and door counts computed directly from python-side data
    wall_count = sum(1 for item in drawn_elements if isinstance(item, dict) and item.get("type") == "wall")
    door_count = sum(1 for item in drawn_elements if isinstance(item, dict) and item.get("type") == "door")

    # --- SIDEBAR (Controls & Inventory) ---
    with st.sidebar:
        st.title("Controls")
        st.markdown(f"**Project:** `{data.get('plan_name', 'Renovation')}`")
        
        if st.button("↩️ Re-Calibrate Scale", use_container_width=True):
            st.session_state.app_stage = "calibrate"
            st.rerun()
        if st.button("🚪 Exit to Start", use_container_width=True):
            st.session_state.app_stage = "onboarding"
            st.rerun()

        st.markdown("---")
        st.header("Architectural Inspector")
        m1, m2 = st.columns(2)
        m1.metric("Walls Drawn", wall_count)
        m2.metric("Doors Drawn", door_count)

        # Update the main project data object with the latest vectors from the canvas
        data["raw_vectors"] = drawn_elements

        st.markdown("---")
        st.header("Save Project")
        st.download_button(
            label="💾 Export Project (.json)",
            data=json.dumps(data, indent=2),
            file_name=f"{data.get('plan_name', 'project').lower().replace(' ', '_')}.json",
            mime="application/json",
            use_container_width=True
        )

    # --- MAIN VIEW: WORKSPACE CAD STUDIO ---
    st.title("🛠️ Shape Editor")

    if image is not None and img_b64 is not None:
        max_w = 1400
        display_w = max(max_w, image.width)
        display_h = 600

        html_template = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Interior Designer</title>
        <style>
        * {{ box-sizing: border-box; }}
        body {{
          margin: 0;
          font: 14px system-ui, sans-serif;
          color: #203044;
          background: #eef2f6;
        }}
        header {{
          display: flex;
          flex-direction: column;
          gap: -1px;
          flex-wrap: wrap;
          padding: 12px;
          background: white;
          border-bottom: 1px solid #d9e1e9;
        }}
        button, select, input {{
          font: inherit;
          padding: 7px 9px;
          border: 1px solid #c7d1dc;
          border-radius: 6px;
          background: white;
        }}
        button {{ cursor: pointer; }}
        button:hover {{ background: #f1f5f9; }}
        button.active {{ background: #2563eb; color: white; border-color: #2563eb; }}
        input[type="number"] {{ width: 72px; }}
        input[type="color"] {{ padding: 2px; width: 38px; height: 32px; cursor: pointer; }}

        main {{
          display: flex;
          height: calc(100dvh - 140px);
          min-height: 420px;
        }}
        aside {{
          width: 250px;
          flex-shrink: 0;
          padding: 14px;
          overflow-y: auto;
          border-right: 1px solid #d9e1e9;
          background: #f8fafc;
        }}
        h3 {{ margin: 0 0 10px; font-size: 15px; }}
        h4 {{ margin: 0 0 8px; font-size: 13px; color: #1e293b; }}

        .section-box {{
          padding: 10px;
          margin-bottom: 12px;
          border: 1px solid #cbd5e1;
          border-radius: 8px;
          background: white;
        }}
        .input-row {{
          display: flex;
          flex-direction: column;
          gap: 4px;
          margin-bottom: 8px;
        }}
        .input-row label {{
          font-size: 12px;
          color: #475569;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }}
        .input-group {{
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 6px;
          margin-bottom: 8px;
        }}
        .input-group label {{
          font-size: 11px;
          color: #475569;
          display: flex;
          flex-direction: column;
          gap: 2px;
        }}
        .input-group input {{ width: 100%; }}

        .item {{
          padding: 9px 10px;
          margin-bottom: 6px;
          border: 1px solid #cdd7e2;
          border-radius: 7px;
          background: white;
          cursor: grab;
          user-select: none;
        }}
        .item:hover {{ border-color: #94a3b8; }}
        .item small {{ display: block; color: #64748b; margin-top: 3px; font-size: 11px; }}
        .help {{ color: #526276; font-size: 12px; line-height: 1.5; margin-top: 14px; }}

        #stage {{ position: relative; flex: 1; min-width: 0; }}
        canvas {{
          display: block;
          width: 100%;
          height: 100%;
          touch-action: none;
        }}
        #badge {{
          position: absolute;
          top: 10px;
          left: 12px;
          padding: 7px 10px;
          background: #ffffffed;
          border: 1px solid #d9e1e9;
          border-radius: 6px;
          font-size: 12px;
          font-weight: 500;
          pointer-events: none;
          box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        footer {{
          padding: 10px 14px;
          background: white;
          border-top: 1px solid #d9e1e9;
          line-height: 1.5;
        }}
        </style>
        </head>
        <body>

        <header>
        <div>
        <button id="select" class="active">Select / Move</button>
        <button id="rotate">Rotate / Flip</button>
        <button id="remove">Delete</button>
        <button id="clear">Clear</button>
        <button id="view">3D preview</button>
        <button id="fit">Fit view</button>
        </div>
        <BR>
        <div>
        <label>Grid
        <select id="grid">
        <option value="auto">Auto</option>
        <option value="0.1">0.1 m</option>
        <option value="0.05">0.05 m</option>
        <option value="0.01">0.01 m</option>
        </select>
        </label>
        <button id="wall">Draw wall</button>
        <button id="door">Add door</button>
        <label>Door width
        <input id="doorWidth" type="number" min="0.4" max="2.4" step="0.05" value="0.8"> m
        </label>
        </div>
        </header>

        <main>
        <aside>
        <!-- Selected Object Inspector -->
        <div id="inspector" class="section-box" style="display:none; background:#eff6ff; border-color:#93c5fd;">
        <h4>Selected Furniture</h4>
        <div class="input-row">
        <label>Name <input id="inspName" type="text" style="width:100%"></label>
        </div>
        <div class="input-group">
        <label>Length (m) <input id="inspW" type="number" step="0.05" min="0.2" max="15"></label>
        <label>Width (m) <input id="inspD" type="number" step="0.05" min="0.2" max="15"></label>
        </div>
        <div class="input-group">
        <label>Height (m) <input id="inspH" type="number" step="0.05" min="0.1" max="5"></label>
        <label>Color <input id="inspColor" type="color"></label>
        </div>
        </div>

        <!-- Custom Furniture Creator -->
        <div class="section-box">
        <h4>Custom Furniture</h4>
        <div class="input-row">
        <label>Name <input id="custName" type="text" value="Custom Desk" style="width:100%"></label>
        </div>
        <div class="input-group">
        <label>Length (m) <input id="custW" type="number" value="1.60" step="0.05" min="0.2" max="15"></label>
        <label>Width (m) <input id="custD" type="number" value="0.80" step="0.05" min="0.2" max="15"></label>
        </div>
        <div class="input-group">
        <label>Height (m) <input id="custH" type="number" value="0.75" step="0.05" min="0.1" max="5"></label>
        <label>Color <input id="custColor" type="color" value="#7ea8d8"></label>
        </div>
        <button id="addCustom" type="button" style="width:100%; background:#2563eb; color:white; font-weight:500;">
                + Add to Plan
        </button>
        <div id="customDraggable" class="item" draggable="true" style="margin-top:8px; text-align:center; font-size:12px; background:#f1f5f9;">
                Or drag this box to stage
        </div>
        </div>

        <h3>Standard Furniture</h3>
        <div id="palette"></div>

        <p class="help">
        <b>Draw wall:</b> drag from start to end.<br>
              • Wall ends automatically <b>snap to nearby walls & corners</b>.<br>
              • Hold <b>Shift</b> for orthogonal lock.<br><br>
        <b>Select / Move:</b> click furniture then drag.<br>
              • <b>Blue dot:</b> rotate furniture (360°).<br>
              • <b>Orange square:</b> resize furniture.<br>
              • <b style="color:#dc2626">Red highlight:</b> furniture overlaps walls or other furniture.<br>
        <b>Add door:</b> click a wall.<br>
        <b>R:</b> rotate furniture or flip door swing.<br>
        <b>Delete:</b> remove selection.<br>
        <b>Mouse wheel:</b> zoom.<br>
        <b>Space + drag:</b> pan (2D).<br>
        <b>3D preview:</b> left‑drag rotates around room, right‑drag pans, wheel zooms.
        </p>
        </aside>

        <div id="stage">
        <canvas id="canvas"></canvas>
        <div id="badge"></div>
        </div>
        </main>

        <footer id="status">
          Draw a room or modify the layout. All measurements are in metres.
        </footer>

        <script>
        "use strict";

        const $ = id => document.getElementById(id);
        const canvas = $("canvas");
        const ctx = canvas.getContext("2d");
        const bgImg = new Image();
        bgImg.src = "{img_b64}";

        const catalog = {{
        sofa:    {{ name:"Sofa",    w:2.1,  d:0.9,  h:0.8,  color:"#80a9d4" }},
        bed:     {{ name:"Bed",     w:1.5,  d:2.0,  h:0.55, color:"#b6a1d5" }},
        table:   {{ name:"Table",   w:1.4,  d:0.8,  h:0.75, color:"#d6ad78" }},
        chair:   {{ name:"Chair",   w:0.5,  d:0.5,  h:0.8,  color:"#e1bd89" }},
        desk:    {{ name:"Desk",    w:1.2,  d:0.6,  h:0.75, color:"#b7a184" }},
        cabinet: {{ name:"Cabinet", w:1.0,  d:0.45, h:1.8,  color:"#a9b8c7" }},
        bath:    {{ name:"Bath",    w:0.75, d:1.7,  h:0.55, color:"#9ed4dd" }},
        toilet:  {{ name:"Toilet",  w:0.4,  d:0.7,  h:0.7,  color:"#c4dce2" }},
        sink:    {{ name:"Sink",    w:0.6,  d:0.45, h:0.85, color:"#a6cbd7" }}
        }};

        let serial = 0;
        const uid = () => "object-" + (++serial);

        let walls = [], doors = [], furniture = [];
        let selected = null;
        let tool = "select";
        let iso = false; // false = 2D editing, true = 3D preview
        let space = false;
        let gesture = null;
        let draft = null;
        let activeSnap = null;
        let azimuth = Math.PI / 4; // rotation in 3D
        let target = {{ x: 0, y: 0, z: 0 }}; // center of model

        let width = 800, height = 600;
        let camera = {{ x: 0, y: 0 }};
        
        // --- SCALE & IMAGE DIMENSIONS (from Python) ---
        const scaleCmPerPx = {scale_cm_per_px};
        let scale = 100.0 / scaleCmPerPx; // pixels per meter
        const imagePixelWidth = {img_px_w};
        const imagePixelHeight = {img_px_h};

        const WALL_THICKNESS = 0.12;
        const CUTAWAY_HEIGHT = 1.1;
        const EPS = 1e-8;

        function notify(text) {{ $("status").textContent = text; }}

        function round2(v) {{ return Math.round(v * 100) / 100; }}

        function syncElementsWithStreamlit() {{
            const allElements = [
                ...walls.map(o => ({{...o, type: 'wall'}})),
                ...doors.map(o => ({{...o, type: 'door'}})),
                ...furniture.map(o => ({{...o, type: 'furniture'}}))
            ];
            const url = new URL(window.parent.location.href);
            url.searchParams.set("raw_elements", JSON.stringify(allElements));
            window.parent.history.replaceState(null, '', url.toString());
        }}
          
        function gridStep() {{
        const value = $("grid").value;
        if (value !== "auto") return Number(value);
        if (scale >= 600) return 0.01;
        if (scale >= 120) return 0.05;
        return 0.1;
        }}

        function snap(p) {{
        const q = gridStep();
        return {{
        x: Math.round(p.x / q) * q,
        y: Math.round(p.y / q) * q
          }};
        }}

        /* --- Wall Matching & Snapping --- */
        function snapWallPoint(rawP, origin = null, useShift = false) {{
        let p = {{ ...rawP }};

        if (origin && useShift) {{
        if (Math.abs(p.x - origin.x) > Math.abs(p.y - origin.y)) {{
        p.y = origin.y;
            }} else {{
        p.x = origin.x;
            }}
          }}

        const snapThreshold = Math.max(0.20, 18 / scale);
        let bestSnap = null;
        let bestDist = snapThreshold;

        for (const w of walls) {{
        for (const pt of [w.a, w.b]) {{
        const d = distance(p, pt);
        if (d < bestDist) {{
        bestDist = d;
        bestSnap = {{ x: pt.x, y: pt.y, type: "vertex", target: pt }};
              }}
            }}
          }}

        if (!bestSnap) {{
        for (const w of walls) {{
        const hit = projectOnWall(p, w);
        if (hit.distance < snapThreshold && hit.distance < bestDist) {{
        bestDist = hit.distance;
        bestSnap = {{ x: hit.point.x, y: hit.point.y, type: "edge", target: hit.point }};
              }}
            }}
          }}

        if (bestSnap) {{
        return {{ point: {{ x: bestSnap.x, y: bestSnap.y }}, snapInfo: bestSnap }};
          }}

        return {{ point: snap(p), snapInfo: null }};
        }}

        function screen(p, z = 0) {{
        if (!iso) {{
        return {{ x: camera.x + p.x * scale,
        y: camera.y + p.y * scale }};
          }}

        const dx = p.x - target.x;
        const dy = p.y - target.y;
        const dz = z - target.z;

        const cosA = Math.cos(azimuth), sinA = Math.sin(azimuth);
        const xr = dx * cosA - dy * sinA;
        const yr = dx * sinA + dy * cosA;
        const zr = dz;

        return {{
        x: camera.x + (xr - yr) * 0.8660254 * scale,
        y: camera.y + ((xr + yr) * 0.5 - zr) * scale
          }};
        }}

        function world(p) {{
        if (!iso) return {{
        x: (p.x - camera.x) / scale,
        y: (p.y - camera.y) / scale
          }};
        return {{ x: 0, y: 0 }};
        }}

        function mouse(e) {{
        const rect = canvas.getBoundingClientRect();
        return {{ x: e.clientX - rect.left, y: e.clientY - rect.top }};
        }}

        function distance(a, b) {{ return Math.hypot(a.x - b.x, a.y - b.y); }}

        function wallInfo(w) {{
        const length = distance(w.a, w.b);
        return {{
        length,
        ux: length > 0 ? (w.b.x - w.a.x) / length : 0,
        uy: length > 0 ? (w.b.y - w.a.y) / length : 0
          }};
        }}

        function along(w, t) {{
        return {{
        x: w.a.x + (w.b.x - w.a.x) * t,
        y: w.a.y + (w.b.y - w.a.y) * t
          }};
        }}

        function projectOnWall(p, w) {{
        const dx = w.b.x - w.a.x, dy = w.b.y - w.a.y;
        const lenSq = dx * dx + dy * dy;
        if (lenSq === 0) return {{ t: 0, point: {{ ...w.a }}, distance: distance(p, w.a) }};
        const t = Math.max(0, Math.min(1, ((p.x - w.a.x) * dx + (p.y - w.a.y) * dy) / lenSq));
        const pt = along(w, t);
        return {{ t, point: pt, distance: distance(p, pt) }};
        }}

        function nearestWall(p) {{
        let best = null;
        for (const w of walls) {{
        const hit = projectOnWall(p, w);
        if (!best || hit.distance < best.distance) best = {{ ...hit, wall: w }};
          }}
        return best;
        }}

        function furniturePoint(f, x, y) {{
        const c = Math.cos(f.angle), s = Math.sin(f.angle);
        return {{ x: f.x + x * c - y * s, y: f.y + x * s + y * c }};
        }}

        function footprint(f) {{
        return [
        furniturePoint(f, -f.w / 2, -f.d / 2),
        furniturePoint(f,  f.w / 2, -f.d / 2),
        furniturePoint(f,  f.w / 2,  f.d / 2),
        furniturePoint(f, -f.w / 2,  f.d / 2)
          ];
        }}

        function insideFurniture(p, f) {{
        const dx = p.x - f.x, dy = p.y - f.y;
        const c = Math.cos(f.angle), s = Math.sin(f.angle);
        return Math.abs(dx * c + dy * s) <= f.w / 2 &&
        Math.abs(-dx * s + dy * c) <= f.d / 2;
        }}

        function toLocal(f, p) {{
        const dx = p.x - f.x, dy = p.y - f.y;
        const c = Math.cos(-f.angle), s = Math.sin(-f.angle);
        return {{ x: dx * c - dy * s, y: dx * s + dy * c }};
        }}

        /* ==========================================================================
           Collision & Overlap Detection (SAT & Polygon Intersection)
           ========================================================================== */

        function isPointInPoly(pt, poly) {{
          let inside = false;
          for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {{
            const xi = poly[i].x, yi = poly[i].y;
            const xj = poly[j].x, yj = poly[j].y;
            const intersect = ((yi > pt.y) !== (yj > pt.y)) &&
              (pt.x < (xj - xi) * (pt.y - yi) / (yj - yi + 1e-12) + xi);
            if (intersect) inside = !inside;
          }}
          return inside;
        }}

        function segmentsIntersect(p1, p2, p3, p4) {{
          function ccw(a, b, c) {{
            return (c.y - a.y) * (b.x - a.x) > (b.y - a.y) * (c.x - a.x);
          }}
          return (ccw(p1, p3, p4) !== ccw(p2, p3, p4)) && (ccw(p1, p2, p3) !== ccw(p1, p2, p4));
        }}

        function polygonsOverlap(poly1, poly2) {{
          // Check if any edges intersect
          for (let i = 0; i < poly1.length; i++) {{
            const a1 = poly1[i], a2 = poly1[(i + 1) % poly1.length];
            for (let j = 0; j < poly2.length; j++) {{
              const b1 = poly2[j], b2 = poly2[(j + 1) % poly2.length];
              if (segmentsIntersect(a1, a2, b1, b2)) return true;
            }}
          }}
          // Check if one polygon is strictly contained inside the other
          if (isPointInPoly(poly1[0], poly2)) return true;
          if (isPointInPoly(poly2[0], poly1)) return true;
          return false;
        }}

        // Compute set of furniture IDs that collide with walls or other furniture
        function getCollidingFurnitureIds() {{
          const colliding = new Set();
          const fFootprints = new Map();
          furniture.forEach(f => fFootprints.set(f.id, footprint(f)));

          // 1. Furniture vs Furniture collision
          for (let i = 0; i < furniture.length; i++) {{
            for (let j = i + 1; j < furniture.length; j++) {{
              const f1 = furniture[i], f2 = furniture[j];
              if (polygonsOverlap(fFootprints.get(f1.id), fFootprints.get(f2.id))) {{
                colliding.add(f1.id);
                colliding.add(f2.id);
              }}
            }}
          }}

          // 2. Furniture vs Wall collision (against wall thickness footprint)
          const wallPolys = walls.map(w => wallFootprint(w, 0, 1));
          for (const f of furniture) {{
            const polyF = fFootprints.get(f.id);
            for (const polyW of wallPolys) {{
              if (polygonsOverlap(polyF, polyW)) {{
                colliding.add(f.id);
                break;
              }}
            }}
          }}

          return colliding;
        }}

        function polygon(points, fill, stroke = "#506176", lineWidth = 1) {{
        ctx.beginPath();
        points.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y));
        ctx.closePath();
        if (fill) {{ ctx.fillStyle = fill; ctx.fill(); }}
        if (stroke) {{
        ctx.strokeStyle = stroke;
        ctx.lineWidth = lineWidth;
        ctx.stroke();
          }}
        }}

        function line(a, b, color = "#334155", lineWidth = 1) {{
        ctx.beginPath();
        ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = color; ctx.lineWidth = lineWidth;
        ctx.stroke();
        }}

        function textAt(text, p, color = "#334155") {{
        ctx.font = "12px system-ui";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = color;
        ctx.fillText(text, p.x, p.y);
        }}

        function prism(points, h, color, selectedObject = false, transparent = false) {{
        const bottom = points.map(p => screen(p));
        const top = points.map(p => screen(p, h));
        const faces = points.map((p, i) => {{
        const j = (i + 1) % points.length;
        return {{
        i, j,
        depth: (p.x + p.y + points[j].x + points[j].y) / 2
            }};
          }}).sort((a, b) => a.depth - b.depth);

        if (transparent) ctx.globalAlpha = 0.5;

        for (const {{ i, j }} of faces) {{
        polygon([bottom[i], bottom[j], top[j], top[i]], color);
        polygon([bottom[i], bottom[j], top[j], top[i]], "rgba(0,0,0,0.10)", null);
          }}
        polygon(top, color, selectedObject ? "#2563eb" : "#506176", selectedObject ? 3 : 1);

        if (transparent) ctx.globalAlpha = 1.0;
        }}

        function wallFootprint(w, t0, t1) {{
        const a = along(w, t0), b = along(w, t1);
        const {{ ux, uy }} = wallInfo(w);
        const nx = -uy * WALL_THICKNESS / 2, ny = ux * WALL_THICKNESS / 2;
        return [
            {{ x: a.x + nx, y: a.y + ny }}, {{ x: b.x + nx, y: b.y + ny }},
            {{ x: b.x - nx, y: b.y - ny }}, {{ x: a.x - nx, y: a.y - ny }}
          ];
        }}

        function solidWallSegments(w) {{
        const L = wallInfo(w).length;
        if (L === 0) return [];
        const openings = doors.filter(d => d.wallId === w.id)
            .map(d => [d.t - d.width / (2 * L), d.t + d.width / (2 * L)])
            .sort((a, b) => a[0] - b[0]);
        let cursor = 0;
        const segments = [];
        for (const [start, end] of openings) {{
        if (start > cursor) segments.push([cursor, start]);
        cursor = Math.max(cursor, end);
          }}
        if (cursor < 1) segments.push([cursor, 1]);
        return segments;
        }}

        function drawGrid() {{
            const step = gridStep();
            const a = world({{ x: 0, y: 0 }});
            const b = world({{ x: width, y: height }});

            if (!iso) {{
                const firstX = Math.floor(a.x / step) * step;
                const lastX = Math.ceil(b.x / step) * step;
                const firstY = Math.floor(a.y / step) * step;
                const lastY = Math.ceil(b.y / step) * step;
                
                for (let x = firstX; x <= lastX; x += step) {{
                    const major = Math.abs(x - Math.round(x)) < EPS;
                    line(screen({{ x, y: firstY }}), screen({{ x, y: lastY }}),
                        major ? "#c5d0dd" : "#e4eaf1", major ? 1.2 : 0.6);
                }}
                for (let y = firstY; y <= lastY; y += step) {{
                    const major = Math.abs(y - Math.round(y)) < EPS;
                    line(screen({{ x: firstX, y }}), screen({{ x: lastX, y }}),
                        major ? "#c5d0dd" : "#e4eaf1", major ? 1.2 : 0.6);
                }}
            }} else {{
                const modelPoints = [
                    ...walls.flatMap(w => [w.a, w.b]),
                    ...furniture.flatMap(footprint)
                ];
                if (modelPoints.length === 0) modelPoints.push({{ x: 0, y: 0 }}, {{ x: 5, y: 4 }});
                let mnX = Infinity, mxX = -Infinity, mnY = Infinity, mxY = -Infinity;
                for (const p of modelPoints) {{
                    mnX = Math.min(mnX, p.x); mxX = Math.max(mxX, p.x);
                    mnY = Math.min(mnY, p.y); mxY = Math.max(mxY, p.y);
                }}
                const minX = Math.floor((mnX - 3) / step) * step;
                const maxX = Math.ceil((mxX + 3) / step) * step;
                const minY = Math.floor((mnY - 3) / step) * step;
                const maxY = Math.ceil((mxY + 3) / step) * step;
                for (let x = minX; x <= maxX; x += step) {{
                    line(screen({{ x, y: minY }}), screen({{ x, y: maxY }}), "#c5d0dd", 0.6);
                }}
                for (let y = minY; y <= maxY; y += step) {{
                    line(screen({{ x: minX, y }}), screen({{ x: maxX, y }}), "#c5d0dd", 0.6);
                }}
            }}
        }}

        function drawDoor(d) {{
        const w = walls.find(w => w.id === d.wallId);
        if (!w) return;
        const {{ length: L, ux, uy }} = wallInfo(w);
        const hinge = along(w, d.t - d.width / (2 * L));
        const closed = along(w, d.t + d.width / (2 * L));
        const nx = -uy * d.swing, ny = ux * d.swing;
        const opened = {{ x: hinge.x + nx * d.width, y: hinge.y + ny * d.width }};
        const color = selected?.id === d.id ? "#2563eb" : "#b7791f";

        line(screen(hinge), screen(closed), "#c99a57", 2);
        line(screen(hinge), screen(opened), color, 3);
        ctx.beginPath();
        for (let i = 0; i <= 24; i++) {{
        const angle = (i / 24) * Math.PI / 2;
        const p = screen({{
        x: hinge.x + d.width * (ux * Math.cos(angle) + nx * Math.sin(angle)),
        y: hinge.y + d.width * (uy * Math.cos(angle) + ny * Math.sin(angle))
            }});
        if (!i) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y);
          }}
        ctx.setLineDash([4, 3]);
        ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.stroke();
        ctx.setLineDash([]);
        }}

        function drawFurniture2D(f, isColliding) {{
        const chosen = selected?.id === f.id;
        // If colliding, display red warning fill and red border
        const fillColor = isColliding ? "#ef4444" : f.color;
        const strokeColor = chosen ? "#2563eb" : (isColliding ? "#b91c1c" : "#506176");
        const strokeWidth = (chosen || isColliding) ? 3 : 1;

        polygon(footprint(f).map(p => screen(p)), fillColor, strokeColor, strokeWidth);

        const segment = (x1, y1, x2, y2) =>
        line(screen(furniturePoint(f, x1, y1)),
        screen(furniturePoint(f, x2, y2)), "#ffffff", 2);

        if (f.type === "bed") {{
        segment(-f.w / 2, -f.d / 2 + 0.4, f.w / 2, -f.d / 2 + 0.4);
        segment(0, -f.d / 2, 0, -f.d / 2 + 0.4);
          }} else if (f.type === "sofa") {{
        segment(-f.w / 2, -f.d / 2 + 0.2, f.w / 2, -f.d / 2 + 0.2);
        segment(-f.w / 6, -f.d / 2 + 0.2, -f.w / 6, f.d / 2);
        segment( f.w / 6, -f.d / 2 + 0.2,  f.w / 6, f.d / 2);
          }}

        if (scale * f.w > 40) textAt(f.name || "Item", screen(f), isColliding ? "#ffffff" : "#334155");

        // Draw rotation & resize handles (only in 2D)
        if (chosen && !iso) {{
        ctx.save();
        ctx.translate(screen(f).x, screen(f).y);
        ctx.rotate(f.angle);

        // Blue rotation handle
        const rhDist = (f.d / 2) * scale + 25;
        ctx.strokeStyle = "#3498db";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(0, -rhDist);
        ctx.stroke();
        ctx.fillStyle = "#3498db";
        ctx.beginPath();
        ctx.arc(0, -rhDist, 9, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 2;
        ctx.stroke();

        // Orange resize handle
        const shX = (f.w / 2) * scale;
        const shY = (f.d / 2) * scale;
        ctx.fillStyle = "#e67e22";
        ctx.fillRect(shX - 10, shY - 10, 20, 20);
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 2;
        ctx.strokeRect(shX - 10, shY - 10, 20, 20);

        ctx.restore();
          }}
        }}

        function render() {{
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = "#f8fafc";
        ctx.fillRect(0, 0, width, height);
        
        if (!iso && bgImg.complete) {{
            // Calculate image size in world meters, then convert to screen pixels
            const imgWorldWidth = imagePixelWidth * scaleCmPerPx / 100.0;
            const imgWorldHeight = imagePixelHeight * scaleCmPerPx / 100.0;
            
            // Get screen coordinates for the top-left (0,0) and bottom-right of the image
            const p1 = screen({{x: 0, y: 0}});
            const p2 = screen({{x: imgWorldWidth, y: imgWorldHeight}});
            
            ctx.globalAlpha = 0.5;
            ctx.drawImage(bgImg, p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);
            ctx.globalAlpha = 1.0;
        }}

        drawGrid();

        const collidingIds = getCollidingFurnitureIds();

        if (!iso) {{
        for (const w of walls) {{
        for (const [a, b] of solidWallSegments(w)) {{
        polygon(wallFootprint(w, a, b).map(p => screen(p)), "#64748b",
        selected?.id === w.id ? "#2563eb" : "#475569",
        selected?.id === w.id ? 3 : 1);
              }}
        const mid = screen(along(w, 0.5));
        textAt(wallInfo(w).length.toFixed(2) + " m", {{ x: mid.x, y: mid.y - 13 }});
            }}
        doors.forEach(drawDoor);
        furniture.forEach(f => drawFurniture2D(f, collidingIds.has(f.id)));
          }} else {{
        const objects = [];
        for (const w of walls) {{
        for (const [a, b] of solidWallSegments(w)) {{
        const points = wallFootprint(w, a, b);
        objects.push({{
        points, h: CUTAWAY_HEIGHT, color: "#cbd5e1",
        id: w.id,
        depth: points.reduce((sum, p) => sum + p.x + p.y, 0) / 4,
        transparent: true
                }});
              }}
            }}
        for (const f of furniture) {{
        const isColliding = collidingIds.has(f.id);
        objects.push({{
        points: footprint(f), h: f.h, color: isColliding ? "#ef4444" : f.color,
        id: f.id, depth: f.x + f.y,
        transparent: false
              }});
            }}
        doors.forEach(drawDoor);
        objects.sort((a, b) => a.depth - b.depth);
        objects.forEach(o => prism(o.points, o.h, o.color, selected?.id === o.id, o.transparent));
          }}

        if (draft) {{
        line(screen(draft.a), screen(draft.b), "#2563eb", Math.max(2, WALL_THICKNESS * scale));
        const p = screen(draft.b);
        textAt(distance(draft.a, draft.b).toFixed(2) + " m", {{ x: p.x, y: p.y - 18 }}, "#2563eb");
          }}

        if (activeSnap && !iso) {{
        const sp = screen(activeSnap.point);
        ctx.save();
        if (activeSnap.snapInfo?.type === "vertex") {{
        ctx.strokeStyle = "#16a34a";
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, 8, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = "#22c55e";
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, 3, 0, Math.PI * 2);
        ctx.fill();
            }} else if (activeSnap.snapInfo?.type === "edge") {{
        ctx.strokeStyle = "#0891b2";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(sp.x, sp.y - 7);
        ctx.lineTo(sp.x + 7, sp.y);
        ctx.lineTo(sp.x, sp.y + 7);
        ctx.lineTo(sp.x - 7, sp.y);
        ctx.closePath();
        ctx.stroke();
            }}
        ctx.restore();
          }}

        const collisionNote = collidingIds.size > 0 ? " · ⚠️ Overlap detected (red)" : "";
        $("badge").textContent = (iso
        ? "3D preview · left‑drag rotate · right‑drag pan · wheel zoom"
        : `2D plan · Grid ${{gridStep()}} m · ${{Math.round(scale)}} px/m`) + collisionNote;
        }}

        function fitView() {{
            const imgWorldWidth = imagePixelWidth * scaleCmPerPx / 100.0;
            const imgWorldHeight = imagePixelHeight * scaleCmPerPx / 100.0;

            const points = [
                {{x: 0, y: 0}},
                {{x: imgWorldWidth, y: 0}},
                {{x: imgWorldWidth, y: imgWorldHeight}},
                {{x: 0, y: imgWorldHeight}},
                ...walls.flatMap(w => [w.a, w.b]),
                ...furniture.flatMap(footprint)
            ];

            if (iso) {{
                let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
                for (const p of points) {{
                    minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
                    minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
                }}
                target = {{ x: (minX + maxX) / 2, y: (minY + maxY) / 2, z: 0 }};
            }}

            const tempScale = scale;
            scale = 1;

            const projected = points.flatMap(p =>
                iso ? [screen(p), screen(p, 2)] : [screen(p)]
            );
            
            scale = tempScale;

            const minX = Math.min(...projected.map(p => p.x));
            const maxX = Math.max(...projected.map(p => p.x));
            const minY = Math.min(...projected.map(p => p.y));
            const maxY = Math.max(...projected.map(p => p.y));

            const newScaleX = width / (maxX - minX) * 0.9;
            const newScaleY = height / (maxY - minY) * 0.9;
            scale = Math.min(newScaleX, newScaleY);

            if (iso) {{
                const sp = screen(target.x, target.y, target.z);
                camera = {{ x: width / 2 - sp.x, y: height / 2 - sp.y }};
            }} else {{
                const worldCenterX = (minX + maxX) / 2;
                const worldCenterY = (minY + maxY) / 2;
                camera = {{
                    x: width / 2 - worldCenterX * scale,
                    y: height / 2 - worldCenterY * scale
                }};
            }}
            render();
        }}

        function canPlaceDoor(d, w, t) {{
        const L = wallInfo(w).length;
        if (d.width > L - 0.1) return false;
        return !doors.some(other =>
        other.id !== d.id && other.wallId === w.id &&
        Math.abs(other.t - t) * L < (other.width + d.width) / 2 + 0.05
          );
        }}

        function doorPosition(d, w, p) {{
        const L = wallInfo(w).length;
        const margin = (d.width / 2 + 0.05) / L;
        if (margin > 0.5) return null;
        const raw = projectOnWall(p, w).t * L;
        const snapped = Math.round(raw / gridStep()) * gridStep() / L;
        const t = Math.max(margin, Math.min(1 - margin, snapped));
        return canPlaceDoor(d, w, t) ? t : null;
        }}

        function addDoor(p) {{
        const hit = nearestWall(p);
        if (!hit || hit.distance > Math.max(0.15, 12 / scale)) {{
        notify("Click close to a wall to add a door."); return;
          }}
        const doorWidth = Number($("doorWidth").value);
        if (!Number.isFinite(doorWidth) || doorWidth < 0.4 || doorWidth > 2.4) {{
        notify("Choose a door width between 0.4 m and 2.4 m."); return;
          }}
        const d = {{ id: uid(), wallId: hit.wall.id, width: doorWidth, t: 0.5, swing: 1 }};
        const t = doorPosition(d, hit.wall, p);
        if (t === null) {{
        notify("Not enough room here: doors need end clearance and cannot overlap.");
        return;
          }}
        d.t = t; doors.push(d);
        selected = {{ kind: "door", id: d.id }};
        updateInspector();
        notify("Door added. Use Select / Move to slide it along the wall.");
        render();
        syncElementsWithStreamlit();
        }}

        function pick(p) {{
        for (const d of [...doors].reverse()) {{
        const w = walls.find(w => w.id === d.wallId);
        if (!w) continue;
        const hit = projectOnWall(p, w);
        if (hit.distance < Math.max(0.15, 10 / scale) &&
        Math.abs(hit.t - d.t) * wallInfo(w).length <= d.width / 2) {{
        return {{ kind: "door", id: d.id }};
            }}
          }}
        for (const f of [...furniture].reverse()) {{
        if (insideFurniture(p, f)) return {{ kind: "furniture", id: f.id }};
          }}
        const hit = nearestWall(p);
        if (hit && hit.distance < Math.max(0.1, 8 / scale)) {{
        return {{ kind: "wall", id: hit.wall.id }};
          }}
        return null;
        }}

        function selectedObject() {{
        if (!selected) return null;
        const list = selected.kind === "wall" ? walls :
        selected.kind === "door" ? doors : furniture;
        return list.find(o => o.id === selected.id);
        }}

        /* --- Furniture Inspector & Custom Dimensions --- */
        function updateInspector() {{
        const insp = $("inspector");
        if (selected?.kind === "furniture") {{
        const f = selectedObject();
        if (f) {{
        insp.style.display = "block";
        $("inspName").value = f.name || "";
        $("inspW").value = round2(f.w);
        $("inspD").value = round2(f.d);
        $("inspH").value = round2(f.h);
        $("inspColor").value = f.color;
        return;
            }}
          }}
        insp.style.display = "none";
        }}

        $("inspName").addEventListener("input", e => {{
        const f = selectedObject();
        if (f && selected.kind === "furniture") {{ f.name = e.target.value; render(); syncElementsWithStreamlit(); }}
        }});
        $("inspW").addEventListener("input", e => {{
        const f = selectedObject();
        const v = parseFloat(e.target.value);
        if (f && selected.kind === "furniture" && v > 0.1) {{ f.w = v; render(); syncElementsWithStreamlit(); }}
        }});
        $("inspD").addEventListener("input", e => {{
        const f = selectedObject();
        const v = parseFloat(e.target.value);
        if (f && selected.kind === "furniture" && v > 0.1) {{ f.d = v; render(); syncElementsWithStreamlit(); }}
        }});
        $("inspH").addEventListener("input", e => {{
        const f = selectedObject();
        const v = parseFloat(e.target.value);
        if (f && selected.kind === "furniture" && v > 0.05) {{ f.h = v; render(); syncElementsWithStreamlit(); }}
        }});
        $("inspColor").addEventListener("input", e => {{
        const f = selectedObject();
        if (f && selected.kind === "furniture") {{ f.color = e.target.value; render(); syncElementsWithStreamlit(); }}
        }});

        function createCustomFurnitureData() {{
        const name = $("custName").value.trim() || "Custom Item";
        const w = Math.max(0.2, parseFloat($("custW").value) || 1.0);
        const d = Math.max(0.2, parseFloat($("custD").value) || 0.8);
        const h = Math.max(0.1, parseFloat($("custH").value) || 0.75);
        const color = $("custColor").value || "#7ea8d8";
        return {{ name, w, d, h, color, type: "custom" }};
        }}

        $("addCustom").onclick = () => {{
        if (iso) return;
        const data = createCustomFurnitureData();
        const centerWorld = world({{ x: width / 2, y: height / 2 }});
        const p = snap(centerWorld);
        const f = {{ ...data, id: uid(), x: p.x, y: p.y, angle: 0 }};
        furniture.push(f);
        selected = {{ kind: "furniture", id: f.id }};
        setTool("select");
        updateInspector();
        notify(`Added ${{f.name}} (${{f.w}} × ${{f.d}} m). Drag or rotate.`);
        render();
        syncElementsWithStreamlit();
        }};

        const customDrag = $("customDraggable");
        customDrag.addEventListener("dragstart", e => {{
        e.dataTransfer.setData("text/plain", "custom_maker");
        e.dataTransfer.effectAllowed = "copy";
        }});

        function rotateSelected() {{
        if (iso) return;
        const o = selectedObject();
        if (!o) return;
        if (selected.kind === "furniture") o.angle += Math.PI / 2;
        if (selected.kind === "door") o.swing *= -1;
        render();
        syncElementsWithStreamlit();
        }}

        function deleteSelected() {{
        if (iso || !selected) return;
        const {{ kind, id }} = selected;
        if (kind === "wall") {{
        walls = walls.filter(w => w.id !== id);
        doors = doors.filter(d => d.wallId !== id);
          }} else if (kind === "door") {{
        doors = doors.filter(d => d.id !== id);
          }} else {{
        furniture = furniture.filter(f => f.id !== id);
          }}
        selected = null;
        updateInspector();
        render();
        syncElementsWithStreamlit();
        }}

        function setTool(name) {{
        tool = name;
        ["select", "wall", "door"].forEach(id =>
        $(id).classList.toggle("active", id === name)
        );
        }}

        /* --- Hit test for furniture handles --- */
        function hitTestFurniture(p) {{
        const sel = selectedObject();
        if (selected?.kind === "furniture" && sel) {{
        const local = toLocal(sel, p);
        // Blue rotation handle
        const rhY = -sel.d / 2 - 25 / scale;
        if (Math.abs(local.x) < 20 / scale && Math.abs(local.y - rhY) < 25 / scale) {{
        return {{ handle: "rotate", f: sel }};
            }}
        // Orange resize handle
        const shX = sel.w / 2, shY = sel.d / 2;
        if (Math.abs(local.x - shX) < 20 / scale && Math.abs(local.y - shY) < 20 / scale) {{
        return {{ handle: "resize", f: sel }};
            }}
          }}
        for (const f of [...furniture].reverse()) {{
        if (insideFurniture(p, f)) return {{ handle: null, f }};
          }}
        return null;
        }}

        /* --- Pointer Events --- */
        canvas.addEventListener("pointerdown", e => {{
        if (![0, 1, 2].includes(e.button)) return;
        e.preventDefault();
        const m = mouse(e), p = world(m);
        canvas.setPointerCapture(e.pointerId);

        if (iso) {{
        if (e.button === 0) {{
        gesture = {{ kind: "orbit", last: m }};
            }} else {{
        gesture = {{ kind: "pan", start: m, camera: {{ ...camera }} }};
            }}
        return;
          }}

        if (e.button !== 0 || space) {{
        gesture = {{ kind: "pan", start: m, camera: {{ ...camera }} }};
        return;
          }}

        if (tool === "wall") {{
        const snapped = snapWallPoint(p);
        draft = {{ a: snapped.point, b: snapped.point }};
        activeSnap = snapped;
        gesture = {{ kind: "wall" }};
          }} else if (tool === "door") {{
        addDoor(p);
          }} else {{
        const hit = hitTestFurniture(p);
        if (hit?.handle && hit.f) {{
        selected = {{ kind: "furniture", id: hit.f.id }};
        gesture = {{
        kind: hit.handle,
        id: hit.f.id,
        before: {{ x: hit.f.x, y: hit.f.y, w: hit.f.w, d: hit.f.d, angle: hit.f.angle }}
              }};
            }} else {{
        selected = pick(p);
        updateInspector();
        const o = selectedObject();
        if (selected?.kind === "furniture") {{
        gesture = {{ kind: "furniture", object: o, offset: {{ x: p.x - o.x, y: p.y - o.y }} }};
              }} else if (selected?.kind === "door") {{
        gesture = {{ kind: "door", object: o }};
              }}
            }}
        render();
          }}
        }});

        canvas.addEventListener("pointermove", e => {{
        const m = mouse(e), p = world(m);

        if (tool === "wall" && !gesture && !iso) {{
        activeSnap = snapWallPoint(p);
        render();
          }}

        if (!gesture) return;

        if (gesture.kind === "orbit") {{
        const dx = m.x - gesture.last.x;
        azimuth += dx * 0.01;
        camera.x = width / 2;
        camera.y = height / 2;
        gesture.last = m;
        render();
        return;
          }}

        if (gesture.kind === "pan") {{
        camera = {{
        x: gesture.camera.x + m.x - gesture.start.x,
        y: gesture.camera.y + m.y - gesture.start.y
            }};
          }} else if (gesture.kind === "wall") {{
        const snapped = snapWallPoint(p, draft.a, e.shiftKey);
        draft.b = snapped.point;
        activeSnap = snapped;
          }} else if (gesture.kind === "furniture") {{
        const q = snap({{
        x: p.x - gesture.offset.x,
        y: p.y - gesture.offset.y
            }});
        Object.assign(gesture.object, q);
          }} else if (gesture.kind === "door") {{
        const d = gesture.object;
        const w = walls.find(w => w.id === d.wallId);
        if (w) {{
        const t = doorPosition(d, w, p);
        if (t !== null) d.t = t;
            }}
          }} else if (gesture.kind === "rotate") {{
        const f = furniture.find(f => f.id === gesture.id);
        if (f) {{
        const dx = p.x - f.x;
        const dy = p.y - f.y;
        f.angle = Math.atan2(dx, -dy);
            }}
          }} else if (gesture.kind === "resize") {{
        const f = furniture.find(f => f.id === gesture.id);
        if (f) {{
        const local = toLocal(f, p);
        f.w = Math.max(0.2, Math.abs(local.x) * 2);
        f.d = Math.max(0.2, Math.abs(local.y) * 2);
            }}
          }}
        render();
        }});

        canvas.addEventListener("pointerup", () => {{
        if (gesture?.kind === "wall" && draft && distance(draft.a, draft.b) >= 0.1) {{
        const w = {{ id: uid(), a: {{ ...draft.a }}, b: {{ ...draft.b }} }};
        walls.push(w);
        selected = {{ kind: "wall", id: w.id }};
        updateInspector();
        notify("Wall created with connected ends.");
          }}
        // Always sync state after a user interaction finishes
        if(gesture) {{
            syncElementsWithStreamlit();
        }}
        gesture = null;
        draft = null;
        activeSnap = null;
        render();
        }});

        canvas.addEventListener("pointercancel", () => {{
        gesture = null; draft = null; activeSnap = null; render();
        }});

        canvas.addEventListener("contextmenu", e => e.preventDefault());

        canvas.addEventListener("wheel", e => {{
        e.preventDefault();
        if (gesture) return;
        const m = mouse(e);
        const oldScale = scale;
        
        if (!iso) {{
            const anchor = world(m);
            scale = Math.max(20, Math.min(1600, scale * Math.exp(-e.deltaY * 0.001)));
            const after = screen(anchor);
            camera.x += m.x - after.x;
            camera.y += m.y - after.y;
        }} else {{
            scale = Math.max(20, Math.min(1600, scale * Math.exp(-e.deltaY * 0.001)));
            camera.x = width / 2;
            camera.y = height / 2;
        }}
        render();
        }}, {{ passive: false }});

        for (const [type, f] of Object.entries(catalog)) {{
        const item = document.createElement("div");
        item.className = "item";
        item.draggable = true;
        item.innerHTML = `${{f.name}}<small>${{f.w}} × ${{f.d}} m</small>`;
        item.addEventListener("dragstart", e => {{
        e.dataTransfer.setData("text/plain", type);
        e.dataTransfer.effectAllowed = "copy";
          }});
        $("palette").appendChild(item);
        }}

        canvas.addEventListener("dragover", e => {{
        if (!iso) {{
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
          }}
        }});

        canvas.addEventListener("drop", e => {{
        e.preventDefault();
        if (iso) return;
        const type = e.dataTransfer.getData("text/plain");
        const p = snap(world(mouse(e)));
        let f;

        if (type === "custom_maker") {{
        f = {{ ...createCustomFurnitureData(), id: uid(), x: p.x, y: p.y, angle: 0 }};
          }} else if (Object.hasOwn(catalog, type)) {{
        f = {{ ...catalog[type], id: uid(), type, x: p.x, y: p.y, angle: 0 }};
          }} else {{
        return;
          }}

        furniture.push(f);
        selected = {{ kind: "furniture", id: f.id }};
        setTool("select");
        updateInspector();
        notify(`${{f.name}} added. Drag to move; press R to rotate.`);
        render();
        syncElementsWithStreamlit();
        }});

        ["select", "wall", "door"].forEach(id => $(id).onclick = () => setTool(id));
        $("grid").onchange = render;
        $("rotate").onclick = rotateSelected;
        $("remove").onclick = deleteSelected;
        $("fit").onclick = fitView;

        $("view").onclick = () => {{
        iso = !iso;
        gesture = null; draft = null; activeSnap = null;
        $("view").textContent = iso ? "Back to 2D editing" : "3D preview";
        notify(iso ? "3D preview: left‑drag rotate around room, right‑drag pan, wheel zoom. Walls are transparent." : "2D editing enabled.");
        fitView();
        }};

        function designData() {{
        return {{ version: 1, units: "metres", serial, walls, doors, furniture }};
        }}


        $("clear").onclick = () => {{
        if (!confirm("Clear the current design? This cannot be undone.")) return;
        walls = []; doors = []; furniture = [];
        selected = null; gesture = null; draft = null; activeSnap = null;
        updateInspector();
        render();
        syncElementsWithStreamlit();
        }};

        function editingText(e) {{
        return ["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName);
        }}

        window.addEventListener("keydown", e => {{
        if (editingText(e)) return;
        if (e.code === "Space") {{ space = true; e.preventDefault(); }}
        if (e.key === "Delete" || e.key === "Backspace") {{
        e.preventDefault(); deleteSelected();
          }}
        if (e.key.toLowerCase() === "r") rotateSelected();
        if (e.key === "Escape") {{
        gesture = null; draft = null; selected = null; activeSnap = null;
        updateInspector();
        render();
          }}
        }});

        window.addEventListener("keyup", e => {{
        if (e.code === "Space") space = false;
        }});

        window.addEventListener("blur", () => {{
        space = false; gesture = null; draft = null; activeSnap = null; render();
        }});
        
        // Load initial elements if they are passed from streamlit
        const initialElements = {json.dumps(drawn_elements)};
        if (Array.isArray(initialElements) && initialElements.length > 0) {{
            walls = initialElements.filter(e => e.type === 'wall');
            doors = initialElements.filter(e => e.type === 'door');
            furniture = initialElements.filter(e => e.type === 'furniture');
            // Find max serial to avoid ID conflicts
            const maxSerial = Math.max(0, ...initialElements.map(e => parseInt(e.id?.split('-')[1] || 0)));
            serial = maxSerial;
        }}

        let firstResize = true;
        bgImg.onload = () => {{
            new ResizeObserver(() => {{
            const rect = $("stage").getBoundingClientRect();
            const oldWidth = width, oldHeight = height;
            width = rect.width; height = rect.height;
            const dpr = window.devicePixelRatio || 1;
            canvas.width = Math.round(width * dpr);
            canvas.height = Math.round(height * dpr);
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            if (firstResize) {{
                firstResize = false;
                fitView();
            }} else {{
                camera.x += (width - oldWidth) / 2;
                camera.y += (height - oldHeight) / 2;
                render();
            }}
            }}).observe($("stage"));
        }};
        </script>
        </body>
        </html>
        """
        
        components.html(html_template, height=display_h + 30, width=display_w)

    else:
        st.error("No floor plan image loaded. Please return to start and upload an image.")


# -----------------------------------------------------------------------------
# 5. APP ROUTER
# -----------------------------------------------------------------------------
if st.session_state.app_stage == "onboarding":
    show_onboarding_screen()
elif st.session_state.app_stage == "calibrate":
    show_calibration_screen()
else:
    show_workspace()
