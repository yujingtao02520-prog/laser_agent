import os
import sys
import webbrowser
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile, File
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

class UpdateExperimentParams(BaseModel):
    new_episode_id: str
    material: str
    thickness_mm: float
    gas: str
    power_kw: float
    speed_m_min: float
    air_pressure_mpa: float
    focus_mm: float
    nozzle_height_mm: float
    nozzle_diameter_mm: float

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

@app.get("/api/experiments/last")
def read_last_experiment():
    try:
        params = gui_db.get_last_run_parameters()
        if params is None:
            return {}
        return params
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/experiments/{episode_id}/parameters")
def update_experiment_parameters(episode_id: str, params: UpdateExperimentParams):
    try:
        # Check if episode exists
        runs = gui_db.get_all_runs()
        if not any(r['episode_id'] == episode_id for r in runs):
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
            
        gui_db.update_run_parameters(episode_id, params.new_episode_id, params.model_dump())
        return {"status": "success", "episode_id": params.new_episode_id}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
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
@app.post("/api/experiments/{episode_id}/files")
async def upload_inspection_files(
    episode_id: str,
    point_cloud_front: Optional[UploadFile] = None,
    point_cloud_back: Optional[UploadFile] = None,
    point_cloud_left: Optional[UploadFile] = None,
    point_cloud_right: Optional[UploadFile] = None,
    point_cloud_dross: Optional[UploadFile] = None,
    image_front: Optional[UploadFile] = None,
    image_back: Optional[UploadFile] = None,
    image_left: Optional[UploadFile] = None,
    image_right: Optional[UploadFile] = None,
    image_top: Optional[UploadFile] = None,
    image_bottom: Optional[UploadFile] = None
):
    try:
        # Check if episode exists
        runs = gui_db.get_all_runs()
        if not any(r['episode_id'] == episode_id for r in runs):
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
            
        import shutil
        import sqlite3
        
        dest_dir = os.path.join(gui_db.INSPECTION_DIR, episode_id)
        os.makedirs(dest_dir, exist_ok=True)
        
        file_fields = {
            "point_cloud_front": point_cloud_front,
            "point_cloud_back": point_cloud_back,
            "point_cloud_left": point_cloud_left,
            "point_cloud_right": point_cloud_right,
            "point_cloud_dross": point_cloud_dross,
            "image_front": image_front,
            "image_back": image_back,
            "image_left": image_left,
            "image_right": image_right,
            "image_top": image_top,
            "image_bottom": image_bottom
        }
        
        updated_paths = {}
        
        for field_name, upload_file in file_fields.items():
            if upload_file is not None and upload_file.filename:
                ext = os.path.splitext(upload_file.filename)[1]
                dest_filename = f"{episode_id}_{field_name}{ext}"
                dest_path = os.path.join(dest_dir, dest_filename)
                
                # Write file stream
                with open(dest_path, "wb") as f:
                    shutil.copyfileobj(upload_file.file, f)
                    
                # Auto-convert TIF to PNG for Web view support
                if ext.lower() in [".tif", ".tiff"]:
                    png_filename = f"{episode_id}_{field_name}.png"
                    png_path = os.path.join(dest_dir, png_filename)
                    gui_db.convert_tif_to_png(dest_path, png_path)
                    
                rel_path = f"data/inspections/{episode_id}/{dest_filename}"
                updated_paths[field_name] = rel_path
                
        if updated_paths:
            # Update database
            conn = sqlite3.connect(gui_db.DB_FILE)
            cursor = conn.cursor()
            for field_name, rel_path in updated_paths.items():
                cursor.execute(f"UPDATE experiment_runs SET {field_name} = ? WHERE episode_id = ?;", (rel_path, episode_id))
            conn.commit()
            conn.close()
            
            gui_db.sync_data_to_files()
            
        return {"status": "success", "updated_fields": list(updated_paths.keys())}
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

class ScanRequest(BaseModel):
    directory: str

@app.post("/api/archive/scan")
async def api_archive_scan(req: ScanRequest):
    """Scans a local directory on the server and auto-archives matching files."""
    result = gui_db.auto_archive_local_directory(req.directory)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@app.post("/api/archive/upload")
async def api_archive_upload(files: List[UploadFile] = File(...)):
    """Receives multiple uploaded files, archives them in a temp folder, distributes them, and cleans up."""
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    try:
        for f in files:
            if not f.filename:
                continue
            temp_file_path = os.path.join(temp_dir, f.filename)
            with open(temp_file_path, "wb") as buffer:
                shutil.copyfileobj(f.file, buffer)
        
        result = gui_db.auto_archive_local_directory(temp_dir)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.get("/api/experiments/{episode_id}/pointcloud")
def get_experiment_pointcloud(episode_id: str, field: str):
    """Loads, downsamples, and returns point cloud data for high-speed Web previewing."""
    runs = gui_db.get_all_runs()
    matched_run = next((r for r in runs if r["episode_id"] == episode_id), None)
    if not matched_run:
        raise HTTPException(status_code=404, detail="找不到该试验记录")
        
    rel_path = matched_run.get(field)
    if not rel_path:
        raise HTTPException(status_code=400, detail=f"该试验记录未绑定字段 {field}")
        
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    abs_path = os.path.join(project_dir, rel_path)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="找不到物理点云文件")
        
    pts = gui_db.parse_point_cloud(abs_path)
    return {"points": pts.tolist()}

@app.post("/api/surface/morphology")
def analyze_surface_morphology(points: List[List[float]]):
    """Calculate morphology metrics for the point cloud currently shown in the UI."""
    try:
        pts = np.asarray(points, dtype=np.float32)
        return gui_db.analyze_surface_morphology(pts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/api/experiments/{episode_id}/surface-process")
def process_full_resolution_surface(episode_id: str, field: str):
    """Extract and analyze the original-resolution surface, returning a safe render sample."""
    runs = gui_db.get_all_runs()
    matched_run = next((r for r in runs if r["episode_id"] == episode_id), None)
    if not matched_run:
        raise HTTPException(status_code=404, detail="找不到该试验记录")
    rel_path = matched_run.get(field)
    if not rel_path or "point_cloud" not in field:
        raise HTTPException(status_code=400, detail="请选择有效的点云字段")

    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    abs_path = os.path.join(project_dir, rel_path)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="找不到物理点云文件")

    try:
        result = gui_db.extract_full_resolution_surface(abs_path)
        surface = result.pop("surface_points")
        morphology = gui_db.analyze_surface_morphology(surface)
        display_points = gui_db.downsample_point_cloud(surface, target_count=100_000)
        return {
            **result,
            "render_point_count": int(len(display_points)),
            "display_points": display_points.tolist(),
            "morphology": morphology,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

# Mount static files
data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
app.mount("/data", StaticFiles(directory=data_dir), name="data")
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
