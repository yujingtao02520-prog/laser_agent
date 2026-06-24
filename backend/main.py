import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from . import db
from . import vision
from . import recommender
from . import optimizer
from . import llm_client

app = FastAPI(title="Laser Cutting Copilot Decision System API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Input validation models
class RecipeCreate(BaseModel):
    material: str
    thickness: float
    laser_power: float
    speed: float
    gas_type: str
    gas_pressure: float
    focus_position: float
    nozzle: str
    piercing_method: str
    kerf_compensation: float
    operator_note: Optional[str] = ""

class SimulateCutRequest(BaseModel):
    material: str
    thickness: float
    laser_power: float
    speed: float
    gas_type: str
    gas_pressure: float
    focus_position: float
    source_recipe_id: Optional[int] = None

class DiagnoseRequest(BaseModel):
    material: str
    thickness: float
    laser_power: float
    speed: float
    gas_type: str
    gas_pressure: float
    focus_position: float
    quality_report: Dict[str, Any]
    source_recipe_id: Optional[int] = None

# 1. Database Endpoints
@app.get("/api/recipes")
def get_recipes():
    return db.get_all_recipes()

@app.post("/api/recipes")
def create_recipe(recipe: RecipeCreate):
    new_rec = recipe.model_dump()
    new_rec["quality_score"] = 95.0
    new_rec["defect_type"] = "none"
    return db.add_recipe(new_rec)

@app.delete("/api/recipes/{recipe_id}")
def delete_recipe(recipe_id: int):
    success = db.delete_recipe(recipe_id)
    if not success:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return {"status": "success", "message": "Recipe deleted successfully"}

@app.get("/api/materials")
def get_materials():
    recipes = db.get_all_recipes()
    materials = list(set([r["material"] for r in recipes]))
    # For each material, list available expert thicknesses
    mat_dict = {}
    for mat in materials:
        mat_dict[mat] = sorted(list(set([r["thickness"] for r in recipes if r["material"] == mat])))
    return mat_dict

# 2. Pre-Cut Inspection Endpoint
@app.get("/api/precut-inspect")
def get_precut_inspect(material: str, thickness: float):
    return vision.run_precut_inspection(material, thickness)

# 3. Parameter Recommendation Endpoint
@app.get("/api/recommend")
def get_recommendation(
    material: str, 
    thickness: float, 
    max_power: float = 6000.0, 
    max_pressure: float = 20.0
):
    return recommender.recommend_parameters(material, thickness, max_power, max_pressure)

# 4. Simulation Endpoint
@app.post("/api/simulate-cut")
def simulate_cut(req: SimulateCutRequest):
    # Find the target baseline recipe to calculate deviations
    if req.source_recipe_id:
        target = db.get_recipe_by_id(req.source_recipe_id)
    else:
        target = db.find_nearest_recipe(req.material, req.thickness)
        
    if not target:
        # Fallback target if nothing in database
        target = {
            "laser_power": req.laser_power,
            "speed": req.speed,
            "gas_type": req.gas_type,
            "gas_pressure": req.gas_pressure,
            "focus_position": req.focus_position,
            "kerf_compensation": 0.2
        }
        
    report = vision.run_postcut_inspection(
        material=req.material,
        thickness=req.thickness,
        laser_power=req.laser_power,
        speed=req.speed,
        gas_type=req.gas_type,
        gas_pressure=req.gas_pressure,
        focus_position=req.focus_position,
        target=target
    )

    # Log to history
    log_entry = {
        "material": req.material,
        "thickness": req.thickness,
        "laser_power": req.laser_power,
        "speed": req.speed,
        "gas_type": req.gas_type,
        "gas_pressure": req.gas_pressure,
        "focus_position": req.focus_position,
        "quality_score": report["quality_score"],
        "dross_height": report["dross_height"],
        "burning_level": report["burning_level"],
        "penetrated": report["penetrated"]
    }
    db.log_cut_result(log_entry)
    
    return {
        "report": report,
        "target_recipe": target
    }

# 5. Closed-loop Diagnose/Optimize Endpoint
@app.post("/api/diagnose")
def diagnose_parameters(req: DiagnoseRequest):
    if req.source_recipe_id:
        target = db.get_recipe_by_id(req.source_recipe_id)
    else:
        target = db.find_nearest_recipe(req.material, req.thickness)
        
    if not target:
        raise HTTPException(status_code=404, detail="No baseline recipe found to perform diagnosis.")
        
    config = llm_client.load_config()
    
    if config.get("mode") == "llm":
        try:
            suggestions, think_log = llm_client.get_llm_suggestions(
                material=req.material,
                thickness=req.thickness,
                current_power=req.laser_power,
                current_speed=req.speed,
                current_gas_type=req.gas_type,
                current_gas_pressure=req.gas_pressure,
                current_focus=req.focus_position,
                quality_report=req.quality_report,
                target_recipe=target
            )
            return {
                "suggestions": suggestions,
                "target_recipe": target,
                "think_log": think_log
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        suggestions = optimizer.diagnose_and_optimize(
            material=req.material,
            thickness=req.thickness,
            current_power=req.laser_power,
            current_speed=req.speed,
            current_gas_type=req.gas_type,
            current_gas_pressure=req.gas_pressure,
            current_focus=req.focus_position,
            quality_report=req.quality_report,
            target_recipe=target
        )
        return {
            "suggestions": suggestions,
            "target_recipe": target,
            "think_log": None
        }

# 6. History Endpoints
@app.get("/api/history")
def get_history():
    return db.get_history()

@app.delete("/api/history")
def clear_history():
    db.clear_history()
    return {"status": "success", "message": "History cleared"}

# Serve frontend static files
if os.path.exists(FRONTEND_DIR):
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")

@app.get("/")
async def get_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"status": "ok", "message": "Backend running. Please create the frontend directory and index.html."}
