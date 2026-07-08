import os
import sys
import webbrowser
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

# Add src to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import gui_db

app = FastAPI(title="Simple Laser Cutting Experiment Logger")

# Define request schemas
class NewExperimentParams(BaseModel):
    episode_id: Optional[str] = None
    stage: Optional[str] = "manual_run"
    material: Optional[str] = "carbon_steel"
    thickness_mm: Optional[float] = 30.0
    gas: Optional[str] = "air"
    power_kw: float
    speed_m_min: float
    air_pressure_mpa: float
    focus_mm: float
    nozzle_height_mm: Optional[float] = 1.0
    nozzle_diameter_mm: Optional[float] = 4.0
    path_type: Optional[str] = "straight_line"
    cut_through: Optional[bool] = False
    failure_case: Optional[str] = "normal"
    kerf_width_top_mm: Optional[float] = None
    kerf_width_bottom_mm: Optional[float] = None
    taper_mm: Optional[float] = None
    dross_height_max_mm: Optional[float] = None
    dross_height_mean_mm: Optional[float] = None
    roughness_Sa_um: Optional[float] = None
    defect_area_mm2: Optional[float] = None
    manual_comment: Optional[str] = ""
    quality_score: Optional[float] = None

class QualityInspectionUpdate(BaseModel):
    cut_through: bool
    failure_case: str = "normal"
    kerf_width_top_mm: Optional[float] = None
    kerf_width_bottom_mm: Optional[float] = None
    taper_mm: Optional[float] = None
    dross_height_max_mm: Optional[float] = None
    dross_height_mean_mm: Optional[float] = None
    roughness_Sa_um: Optional[float] = None
    defect_area_mm2: Optional[float] = None
    manual_comment: Optional[str] = ""
    quality_score: Optional[float] = None

# API Endpoints
@app.get("/api/experiments")
def read_experiments():
    try:
        return gui_db.get_all_runs()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/experiments")
def log_experiment(params: NewExperimentParams):
    try:
        episode_id = gui_db.add_run(params.model_dump())
        return {"status": "success", "episode_id": episode_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/experiments/{episode_id}")
def delete_experiment(episode_id: str):
    try:
        deleted = gui_db.delete_run(episode_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
        return {"status": "success", "episode_id": episode_id}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/experiments/{episode_id}/quality")
def update_quality(episode_id: str, quality: QualityInspectionUpdate):
    try:
        # Check if episode exists
        runs = gui_db.get_all_runs()
        if not any(r['episode_id'] == episode_id for r in runs):
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
            
        gui_db.update_run_quality(episode_id, quality.model_dump())
        return {"status": "success", "episode_id": episode_id}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze")
def run_analysis():
    """Runs range analysis on the recorded data and returns the summary."""
    try:
        csv_path = gui_db.CSV_FILE
        if not os.path.exists(csv_path):
            raise HTTPException(status_code=404, detail="No experiment log CSV file found to analyze.")
            
        df = pd.read_csv(csv_path)
        if len(df) < 3:
            return {
                "status": "warning",
                "message": "Too few records to perform meaningful range analysis. Add at least 3 runs."
            }
            
        factors = ["power_kw", "speed_m_min", "air_pressure_mpa", "focus_mm"]
        metrics = ["quality_score", "dross_height_max_mm", "roughness_Sa_um"]
        
        # Clean data for factor columns (fill nan with mean/median or drop, but here we assume factors are present)
        df = df.dropna(subset=factors)
        
        analysis_report = {}
        
        for metric in metrics:
            if metric not in df.columns or df[metric].isnull().all():
                continue
                
            metric_data = df.dropna(subset=[metric])
            if metric_data.empty:
                continue
                
            ranges = {}
            k_means = {}
            for factor in factors:
                means = metric_data.groupby(factor)[metric].mean()
                k_means[factor] = {str(k): round(float(v), 3) for k, v in means.items()}
                ranges[factor] = round(float(means.max() - means.min()), 3)
                
            # Rank factors by range descending
            ranking = sorted(ranges.items(), key=lambda x: x[1], reverse=True)
            
            # Determine best level
            best_levels = {}
            for factor in factors:
                means = metric_data.groupby(factor)[metric].mean()
                if metric == "quality_score":
                    # maximize
                    best_val = means.idxmax()
                else:
                    # minimize
                    best_val = means.idxmin()
                best_levels[factor] = round(float(best_val), 3)
                
            analysis_report[metric] = {
                "metric_name": metric,
                "ranges": ranges,
                "factor_ranking": [f"{item[0]} (Range={item[1]})" for item in ranking],
                "k_means": k_means,
                "best_levels": best_levels
            }
            
        # Overall best observed run
        best_observed_row = df.sort_values("quality_score", ascending=False).iloc[0]
        best_observed = {
            "episode_id": best_observed_row["episode_id"],
            "quality_score": float(best_observed_row["quality_score"]) if pd.notnull(best_observed_row["quality_score"]) else None,
            "power_kw": float(best_observed_row["power_kw"]),
            "speed_m_min": float(best_observed_row["speed_m_min"]),
            "air_pressure_mpa": float(best_observed_row["air_pressure_mpa"]),
            "focus_mm": float(best_observed_row["focus_mm"])
        }
        
        return {
            "status": "success",
            "best_observed": best_observed,
            "metrics_analysis": analysis_report
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount static files
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
