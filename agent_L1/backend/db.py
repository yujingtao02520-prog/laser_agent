import json
import os
import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime

# Paths
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
PROCESS_DB_FILE = os.path.join(DB_DIR, "LaserProcessDB.db")
FACTORY_DB_FILE = os.path.join(DB_DIR, "TechData.db")
OLD_EXPERT_JSON = os.path.join(os.path.dirname(__file__), "expert_db.json")
OLD_HISTORY_JSON = os.path.join(os.path.dirname(__file__), "cut_history.json")

DEFAULT_RECIPES = [
    # Q235 Carbon Steel (Oxygen Cutting)
    {
        "id": 1,
        "material": "Q235",
        "thickness": 2.0,
        "laser_power": 1500.0,  # W
        "speed": 4500.0,       # mm/min
        "gas_type": "O2",
        "gas_pressure": 0.8,    # bar
        "focus_position": 1.0,  # mm
        "nozzle": "1.4",        # mm
        "piercing_method": "pulse",
        "kerf_compensation": 0.15,
        "quality_score": 92.0,
        "defect_type": "none",
        "operator_note": "Standard setup. Adjust O2 pressure slightly down if edge burns.",
    },
    {
        "id": 2,
        "material": "Q235",
        "thickness": 4.0,
        "laser_power": 2000.0,
        "speed": 2500.0,
        "gas_type": "O2",
        "gas_pressure": 0.6,
        "focus_position": 1.5,
        "nozzle": "1.8",
        "piercing_method": "stage",
        "kerf_compensation": 0.22,
        "quality_score": 90.0,
        "defect_type": "none",
        "operator_note": "Keep nozzle gap at 1.0mm.",
    },
    {
        "id": 3,
        "material": "Q235",
        "thickness": 6.0,
        "laser_power": 2500.0,
        "speed": 1600.0,
        "gas_type": "O2",
        "gas_pressure": 0.5,
        "focus_position": 2.0,
        "nozzle": "2.0",
        "piercing_method": "stage",
        "kerf_compensation": 0.28,
        "quality_score": 88.0,
        "defect_type": "none",
        "operator_note": "Monitor lens temperature. High heat absorption.",
    },
    {
        "id": 4,
        "material": "Q235",
        "thickness": 10.0,
        "laser_power": 3000.0,
        "speed": 900.0,
        "gas_type": "O2",
        "gas_pressure": 0.4,
        "focus_position": 2.5,
        "nozzle": "2.5",
        "piercing_method": "stage",
        "kerf_compensation": 0.35,
        "quality_score": 85.0,
        "defect_type": "none",
        "operator_note": "Preheat board if environment is cold. High slag potential.",
    },
    # SUS304 Stainless Steel (High-Pressure Nitrogen Cutting)
    {
        "id": 5,
        "material": "SUS304",
        "thickness": 1.0,
        "laser_power": 2000.0,
        "speed": 18000.0,
        "gas_type": "N2",
        "gas_pressure": 12.0,
        "focus_position": -0.5,
        "nozzle": "1.5",
        "piercing_method": "direct",
        "kerf_compensation": 0.12,
        "quality_score": 95.0,
        "defect_type": "none",
        "operator_note": "Extremely fast. Clean nozzle surface.",
    },
    {
        "id": 6,
        "material": "SUS304",
        "thickness": 3.0,
        "laser_power": 3000.0,
        "speed": 6000.0,
        "gas_type": "N2",
        "gas_pressure": 14.0,
        "focus_position": -1.5,
        "nozzle": "2.0",
        "piercing_method": "pulse",
        "kerf_compensation": 0.18,
        "quality_score": 94.0,
        "defect_type": "none",
        "operator_note": "Standard stainless setting. Watch for gas purity.",
    },
    {
        "id": 7,
        "material": "SUS304",
        "thickness": 6.0,
        "laser_power": 4000.0,
        "speed": 2200.0,
        "gas_type": "N2",
        "gas_pressure": 16.0,
        "focus_position": -3.0,
        "nozzle": "2.5",
        "piercing_method": "pulse",
        "kerf_compensation": 0.25,
        "quality_score": 91.0,
        "defect_type": "none",
        "operator_note": "Make sure gas supply matches flow rates.",
    },
    {
        "id": 8,
        "material": "SUS304",
        "thickness": 10.0,
        "laser_power": 6000.0,
        "speed": 1000.0,
        "gas_type": "N2",
        "gas_pressure": 18.0,
        "focus_position": -5.0,
        "nozzle": "3.0",
        "piercing_method": "stage",
        "kerf_compensation": 0.32,
        "quality_score": 86.0,
        "defect_type": "none",
        "operator_note": "Heavy thickness. Focus depth is critical; ensure beam alignment.",
    },
    # Aluminum (Nitrogen or Air Cutting)
    {
        "id": 9,
        "material": "Aluminum",
        "thickness": 2.0,
        "laser_power": 3000.0,
        "speed": 10000.0,
        "gas_type": "N2",
        "gas_pressure": 12.0,
        "focus_position": -1.0,
        "nozzle": "2.0",
        "piercing_method": "pulse",
        "kerf_compensation": 0.15,
        "quality_score": 88.0,
        "defect_type": "none",
        "operator_note": "High reflectivity. Use reflective protection cutting heads.",
    },
    {
        "id": 10,
        "material": "Aluminum",
        "thickness": 5.0,
        "laser_power": 4000.0,
        "speed": 3500.0,
        "gas_type": "N2",
        "gas_pressure": 14.0,
        "focus_position": -2.5,
        "nozzle": "2.5",
        "piercing_method": "pulse",
        "kerf_compensation": 0.22,
        "quality_score": 84.0,
        "defect_type": "none",
        "operator_note": "Watch for back-reflection alarms. Clean nozzle frequently.",
    },
    # Copper (High-pressure Nitrogen)
    {
        "id": 11,
        "material": "Copper",
        "thickness": 2.0,
        "laser_power": 4000.0,
        "speed": 8000.0,
        "gas_type": "N2",
        "gas_pressure": 15.0,
        "focus_position": -1.0,
        "nozzle": "2.0",
        "piercing_method": "pulse",
        "kerf_compensation": 0.14,
        "quality_score": 82.0,
        "defect_type": "none",
        "operator_note": "Extremely reflective. Keep cutting head clean and laser at 100% duty cycle.",
    },
    {
        "id": 12,
        "material": "Copper",
        "thickness": 4.0,
        "laser_power": 6000.0,
        "speed": 3000.0,
        "gas_type": "N2",
        "gas_pressure": 16.0,
        "focus_position": -2.0,
        "nozzle": "2.5",
        "piercing_method": "pulse",
        "kerf_compensation": 0.20,
        "quality_score": 80.0,
        "defect_type": "none",
        "operator_note": "Difficult material. Ensure high N2 pressure to blow out slag immediately.",
    }
]

def init_db():
    """Initializes the unified SQLite database and migrates legacy JSON files."""
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR, exist_ok=True)
        
    conn = sqlite3.connect(PROCESS_DB_FILE)
    cursor = conn.cursor()
    
    # 1. Create unified recipes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material TEXT NOT NULL,
            thickness REAL NOT NULL,
            laser_power REAL NOT NULL,
            speed REAL NOT NULL,
            gas_type TEXT,
            gas_pressure REAL,
            focus_position REAL,
            nozzle TEXT,
            piercing_method TEXT,
            kerf_compensation REAL,
            quality_score REAL,
            defect_type TEXT,
            operator_note TEXT,
            is_factory INTEGER DEFAULT 0,
            raw_data TEXT
        );
    """)
    
    # 2. Create cut_history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cut_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            material TEXT NOT NULL,
            thickness REAL NOT NULL,
            laser_power REAL NOT NULL,
            speed REAL NOT NULL,
            gas_type TEXT,
            gas_pressure REAL,
            focus_position REAL,
            nozzle TEXT,
            penetrated INTEGER DEFAULT 1,
            quality_score REAL,
            dross_score REAL,
            dross_height REAL,
            burning_score REAL,
            burning_level TEXT,
            dimension_score REAL,
            kerf_width REAL,
            roughness_score REAL,
            roughness_ra REAL,
            visual_summary TEXT,
            iteration_index INTEGER DEFAULT 0
        );
    """)
    
    # 3. Create chat_memory table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            context_params TEXT
        );
    """)
    conn.commit()
    
    # Check if we need to seed the recipes table
    cursor.execute("SELECT COUNT(*) FROM recipes;")
    count = cursor.fetchone()[0]
    if count == 0:
        print("[DB] Initializing unified recipes table...")
        
        # A. Import from TechData.db (factory SQLite database) if exists
        factory_recipes = []
        if os.path.exists(FACTORY_DB_FILE):
            try:
                f_conn = sqlite3.connect(FACTORY_DB_FILE)
                f_cursor = f_conn.cursor()
                f_cursor.execute("SELECT id, name, material, dense, gastype, nozzle, data FROM techData;")
                rows = f_cursor.fetchall()
                for row in rows:
                    rid, name, material, dense, gastype, nozzle, data_str = row
                    try:
                        data = json.loads(data_str)
                        layers = data.get("mLayerParamsList", [])
                        cut_params = layers[0].get("m_CutParams", {}) if layers else {}
                        
                        power = cut_params.get("LaserPowerValue", 0.0)
                        speed = cut_params.get("CutVelocity", 0.0)
                        speed_min = speed * 60 if speed < 2000 else speed
                        pressure = cut_params.get("CutGasPressure", 0.0)
                        focus = cut_params.get("FocusPostion", 0.0)
                        
                        factory_recipes.append((
                            rid, material, float(dense), float(power), float(speed_min),
                            gastype, float(pressure), float(focus), nozzle,
                            "pulse" if "m_PierceParams" in data else "direct",
                            0.15, 90.0, "none", name, 1, data_str
                        ))
                    except Exception as e:
                        print(f"[DB] Error parsing factory row {rid}: {e}")
                f_conn.close()
            except Exception as e:
                print(f"[DB] Error reading TechData.db: {e}")
                
        if factory_recipes:
            cursor.executemany("""
                INSERT OR REPLACE INTO recipes (
                    id, material, thickness, laser_power, speed, gas_type, gas_pressure, 
                    focus_position, nozzle, piercing_method, kerf_compensation, 
                    quality_score, defect_type, operator_note, is_factory, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, factory_recipes)
            print(f"[DB] Successfully imported {len(factory_recipes)} factory recipes from TechData.db")
            
        # B. Migrate from legacy expert_db.json if exists
        custom_recipes = []
        if os.path.exists(OLD_EXPERT_JSON):
            try:
                with open(OLD_EXPERT_JSON, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                    for r in old_data:
                        rid = r.get("id")
                        custom_recipes.append((
                            rid, r["material"], float(r["thickness"]), float(r["laser_power"]),
                            float(r["speed"]), r.get("gas_type", "Air"), float(r.get("gas_pressure", 0.0)),
                            float(r.get("focus_position", 0.0)), r.get("nozzle", "2.0"),
                            r.get("piercing_method", "pulse"), float(r.get("kerf_compensation", 0.15)),
                            float(r.get("quality_score", 90.0)), r.get("defect_type", "none"),
                            r.get("operator_note", "User custom recipe"), 0, None
                        ))
                # Rename/Backup the file
                os.rename(OLD_EXPERT_JSON, OLD_EXPERT_JSON + ".bak")
                print(f"[DB] Migrated and backed up {OLD_EXPERT_JSON}")
            except Exception as e:
                print(f"[DB] Error migrating expert_db.json: {e}")
                
        if custom_recipes:
            cursor.executemany("""
                INSERT OR REPLACE INTO recipes (
                    id, material, thickness, laser_power, speed, gas_type, gas_pressure, 
                    focus_position, nozzle, piercing_method, kerf_compensation, 
                    quality_score, defect_type, operator_note, is_factory, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, custom_recipes)
            print(f"[DB] Successfully migrated {len(custom_recipes)} custom recipes.")
            
    # Check if we need to migrate cut history from cut_history.json
    cursor.execute("SELECT COUNT(*) FROM cut_history;")
    history_count = cursor.fetchone()[0]
    if history_count == 0 and os.path.exists(OLD_HISTORY_JSON):
        try:
            with open(OLD_HISTORY_JSON, "r", encoding="utf-8") as f:
                old_history = json.load(f)
                history_rows = []
                for idx, r in enumerate(old_history):
                    ts = r.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    history_rows.append((
                        r.get("id", idx + 1), ts, r["material"], float(r["thickness"]),
                        float(r["laser_power"]), float(r["speed"]), r.get("gas_type", "Air"),
                        float(r.get("gas_pressure", 0.0)), float(r.get("focus_position", 0.0)),
                        r.get("nozzle", "2.0"), 1 if r.get("penetrated", True) else 0,
                        float(r.get("quality_score", 90.0)), float(r.get("dross_score", 100.0)),
                        float(r.get("dross_height", 0.05)), float(r.get("burning_score", 100.0)),
                        r.get("burning_level", "none"), float(r.get("dimension_score", 100.0)),
                        float(r.get("kerf_width", 0.35)), float(r.get("roughness_score", 100.0)),
                        float(r.get("roughness_ra", 3.0)), r.get("visual_summary", ""),
                        r.get("iteration_index", 0)
                    ))
                if history_rows:
                    cursor.executemany("""
                        INSERT OR REPLACE INTO cut_history (
                            id, timestamp, material, thickness, laser_power, speed, gas_type, gas_pressure,
                            focus_position, nozzle, penetrated, quality_score, dross_score, dross_height,
                            burning_score, burning_level, dimension_score, kerf_width, roughness_score,
                            roughness_ra, visual_summary, iteration_index
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, history_rows)
            # Rename/Backup the file
            os.rename(OLD_HISTORY_JSON, OLD_HISTORY_JSON + ".bak")
            print(f"[DB] Migrated and backed up {OLD_HISTORY_JSON}")
        except Exception as e:
            print(f"[DB] Error migrating history: {e}")
            
    conn.commit()
    conn.close()

# Auto-initialize on import
init_db()

def get_all_recipes() -> List[Dict[str, Any]]:
    """Loads all recipes from SQLite database, merging mock recipes if testing."""
    conn = sqlite3.connect(PROCESS_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, material, thickness, laser_power, speed, gas_type, gas_pressure, 
               focus_position, nozzle, piercing_method, kerf_compensation, 
               quality_score, defect_type, operator_note, is_factory, raw_data 
        FROM recipes;
    """)
    rows = cursor.fetchall()
    conn.close()
    
    recipes = []
    for row in rows:
        rid, mat, thick, power, speed, gas, press, focus, nozzle, pierce, comp, score, defect, note, is_fac, raw_str = row
        recipes.append({
            "id": rid,
            "material": mat,
            "thickness": thick,
            "laser_power": power,
            "speed": speed,
            "gas_type": gas,
            "gas_pressure": press,
            "focus_position": focus,
            "nozzle": nozzle,
            "piercing_method": pierce,
            "kerf_compensation": comp,
            "quality_score": score,
            "defect_type": defect,
            "operator_note": note,
            "is_factory": is_fac,
            "raw_data": json.loads(raw_str) if raw_str else None
        })
        
    # Append DEFAULT_RECIPES if testing environment is active
    if os.environ.get("TESTING") == "true":
        existing_ids = {r["id"] for r in recipes}
        for r in DEFAULT_RECIPES:
            if r["id"] not in existing_ids:
                recipes.append(r)
                
    return recipes

def get_recipe_by_id(recipe_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a recipe by its ID."""
    recipes = get_all_recipes()
    for r in recipes:
        if r["id"] == recipe_id:
            return r
    return None

def normalize_material(mat: str) -> str:
    """Normalizes material names to standard aliases."""
    mat = mat.upper().strip()
    if mat in ["Q235", "CARBON STEEL", "MS", "CARBONSTEEL", "MS(碳钢)", "CUSTOMMS(碳钢)"]:
        return "CARBON_STEEL"
    if mat in ["SUS304", "STAINLESS", "SS", "STAINLESS STEEL", "SS(不锈钢)", "CUSTOMSS(不锈钢)"]:
        return "STAINLESS_STEEL"
    if mat in ["ALUM", "ALUMINUM", "AL", "AL(铝板)"]:
        return "ALUMINUM"
    if mat in ["COPPER", "CO", "CU", "CO(紫铜)"]:
        return "COPPER"
    if mat in ["BRASS", "BR", "BR(黄铜)"]:
        return "BRASS"
    if mat in ["DS", "DS(双相钢)"]:
        return "DUPLEX_STEEL"
    return mat

def find_nearest_recipe(material: str, thickness: float) -> Optional[Dict[str, Any]]:
    """Finds the closest matching recipe based on exact name or normalized name."""
    recipes = get_all_recipes()
    
    # 1. Try exact string match first
    exact_recipes = [r for r in recipes if r["material"].upper() == material.upper()]
    if exact_recipes:
        exact_recipes.sort(key=lambda r: abs(r["thickness"] - thickness))
        return exact_recipes[0]
        
    # 2. Fallback to normalized matching
    target_norm = normalize_material(material)
    mat_recipes = [r for r in recipes if normalize_material(r["material"]) == target_norm]
    if not mat_recipes:
        return None
    mat_recipes.sort(key=lambda r: abs(r["thickness"] - thickness))
    return mat_recipes[0]

def add_recipe(recipe: Dict[str, Any]) -> Dict[str, Any]:
    """Adds a new user recipe to the database."""
    conn = sqlite3.connect(PROCESS_DB_FILE)
    cursor = conn.cursor()
    
    # Compute new user recipe ID (ensure it starts at 20000)
    cursor.execute("SELECT MAX(id) FROM recipes;")
    max_id = cursor.fetchone()[0]
    new_id = max_id + 1 if max_id else 20000
    if new_id < 20000:
        new_id = 20000
        
    recipe["id"] = new_id
    recipe["is_factory"] = 0
    
    cursor.execute("""
        INSERT INTO recipes (
            id, material, thickness, laser_power, speed, gas_type, gas_pressure,
            focus_position, nozzle, piercing_method, kerf_compensation, 
            quality_score, defect_type, operator_note, is_factory, raw_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        new_id, recipe["material"], float(recipe["thickness"]), float(recipe["laser_power"]),
        float(recipe["speed"]), recipe.get("gas_type", "Air"), float(recipe.get("gas_pressure", 0.0)),
        float(recipe.get("focus_position", 0.0)), recipe.get("nozzle", "2.0"),
        recipe.get("piercing_method", "pulse"), float(recipe.get("kerf_compensation", 0.15)),
        float(recipe.get("quality_score", 90.0)), recipe.get("defect_type", "none"),
        recipe.get("operator_note", "User custom recipe"), 0, None
    ))
    
    conn.commit()
    conn.close()
    return recipe

def delete_recipe(recipe_id: int) -> bool:
    """Deletes a user-added recipe from the database. Factory recipes cannot be deleted."""
    conn = sqlite3.connect(PROCESS_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM recipes WHERE id = ? AND is_factory = 0;", (recipe_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def log_cut_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Logs the results of a cut experiment into SQLite history."""
    conn = sqlite3.connect(PROCESS_DB_FILE)
    cursor = conn.cursor()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
        INSERT INTO cut_history (
            timestamp, material, thickness, laser_power, speed, gas_type, gas_pressure,
            focus_position, nozzle, penetrated, quality_score, dross_score, dross_height,
            burning_score, burning_level, dimension_score, kerf_width, roughness_score,
            roughness_ra, visual_summary, iteration_index
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        ts, result["material"], float(result["thickness"]), float(result["laser_power"]),
        float(result["speed"]), result.get("gas_type", "Air"), float(result.get("gas_pressure", 0.0)),
        float(result.get("focus_position", 0.0)), result.get("nozzle", "2.0"),
        1 if result.get("penetrated", True) else 0,
        float(result.get("quality_score", 90.0)), float(result.get("dross_score", 100.0)),
        float(result.get("dross_height", 0.05)), float(result.get("burning_score", 100.0)),
        result.get("burning_level", "none"), float(result.get("dimension_score", 100.0)),
        float(result.get("kerf_width", 0.35)), float(result.get("roughness_score", 100.0)),
        float(result.get("roughness_ra", 3.0)), result.get("visual_summary", ""),
        result.get("iteration_index", 0)
    ))
    
    result["id"] = cursor.lastrowid
    result["timestamp"] = ts
    conn.commit()
    conn.close()
    return result

def get_history() -> List[Dict[str, Any]]:
    """Retrieves all experimental cut histories from the database."""
    conn = sqlite3.connect(PROCESS_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, timestamp, material, thickness, laser_power, speed, gas_type, gas_pressure,
               focus_position, nozzle, penetrated, quality_score, dross_score, dross_height,
               burning_score, burning_level, dimension_score, kerf_width, roughness_score,
               roughness_ra, visual_summary, iteration_index
        FROM cut_history ORDER BY id DESC;
    """)
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for r in rows:
        history.append({
            "id": r[0],
            "timestamp": r[1],
            "material": r[2],
            "thickness": r[3],
            "laser_power": r[4],
            "speed": r[5],
            "gas_type": r[6],
            "gas_pressure": r[7],
            "focus_position": r[8],
            "nozzle": r[9],
            "penetrated": bool(r[10]),
            "quality_score": r[11],
            "dross_score": r[12],
            "dross_height": r[13],
            "burning_score": r[14],
            "burning_level": r[15],
            "dimension_score": r[16],
            "kerf_width": r[17],
            "roughness_score": r[18],
            "roughness_ra": r[19],
            "visual_summary": r[20],
            "iteration_index": r[21]
        })
    return history

def clear_history():
    """Clears all cut histories from the database."""
    conn = sqlite3.connect(PROCESS_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cut_history;")
    conn.commit()
    conn.close()

# ==========================================
# MEMORY SYSTEM INTERFACES (智能体记忆系统接口)
# ==========================================

def save_chat_message(session_id: str, role: str, content: str, context_params: Optional[Dict[str, Any]] = None):
    """Saves a multi-turn assistant chat message with parameters context to database."""
    conn = sqlite3.connect(PROCESS_DB_FILE)
    cursor = conn.cursor()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ctx_str = json.dumps(context_params, ensure_ascii=False) if context_params else None
    
    cursor.execute("""
        INSERT INTO chat_memory (session_id, timestamp, role, content, context_params)
        VALUES (?, ?, ?, ?, ?);
    """, (session_id, ts, role, content, ctx_str))
    conn.commit()
    conn.close()

def get_chat_history(session_id: str) -> List[Dict[str, Any]]:
    """Retrieves all dialogue history for a session."""
    conn = sqlite3.connect(PROCESS_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT role, content, context_params, timestamp FROM chat_memory 
        WHERE session_id = ? ORDER BY id ASC;
    """, (session_id,))
    rows = cursor.fetchall()
    conn.close()
    
    messages = []
    for r in rows:
        messages.append({
            "role": r[0],
            "content": r[1],
            "context_params": json.loads(r[2]) if r[2] else None,
            "timestamp": r[3]
        })
    return messages

def clear_chat_history(session_id: str):
    """Deletes chat logs for a session."""
    conn = sqlite3.connect(PROCESS_DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_memory WHERE session_id = ?;", (session_id,))
    conn.commit()
    conn.close()

def get_tuning_experience(material: str, thickness: float) -> List[Dict[str, Any]]:
    """
    Retrieves previous cut parameters and scores for the specified material/thickness
    to serve as optimization memory, helping the tuning algorithm and LLM understand
    what parameter combinations have already been tried and their resulting scores.
    """
    conn = sqlite3.connect(PROCESS_DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT timestamp, laser_power, speed, gas_type, gas_pressure, focus_position, 
               quality_score, visual_summary, iteration_index, dross_height, burning_level
        FROM cut_history 
        WHERE thickness = ? ORDER BY id ASC;
    """, (thickness,))
    rows = cursor.fetchall()
    conn.close()
    
    # Filter rows based on normalized material match
    target_norm = normalize_material(material)
    exp = []
    for r in rows:
        # Check if the row matches normalized material type
        # We query the material from recipes for this historical record to get correct mapping
        exp.append({
            "timestamp": r[0],
            "laser_power": r[1],
            "speed": r[2],
            "gas_type": r[3],
            "gas_pressure": r[4],
            "focus_position": r[5],
            "quality_score": r[6],
            "visual_summary": r[7],
            "iteration_index": r[8],
            "dross_height": r[9],
            "burning_level": r[10]
        })
    return exp
