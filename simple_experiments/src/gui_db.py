import os
import re
import sqlite3
import pandas as pd
from typing import List, Dict, Any, Optional

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_FILE = os.path.join(DB_DIR, "orthogonal_experiments.db")
CSV_FILE = os.path.join(DB_DIR, "experiment_log.csv")
JSON_FILE = os.path.join(DB_DIR, "experiment_log.json")
SOURCE_CSV_FILE = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "正交实验demo", "data", "metadata", "experiment_log.csv"))


def _format_episode_value(value: Any, *, absolute: bool = False) -> str:
    """Format a process value compactly for use in an experiment ID."""
    number = float(value)
    if absolute:
        number = abs(number)
    if number == 0:
        number = 0.0
    return f"{number:.10f}".rstrip("0").rstrip(".")


def build_episode_id(
    sequence: int,
    speed_m_min: Any,
    air_pressure_mpa: Any,
    focus_mm: Any,
) -> str:
    """Build an ID such as ``SY-n001-v5.5-p8-f8``."""
    return (
        f"SY-n{int(sequence):03d}"
        f"-v{_format_episode_value(speed_m_min)}"
        f"-p{_format_episode_value(air_pressure_mpa)}"
        f"-f{_format_episode_value(focus_mm, absolute=True)}"
    )


def extract_episode_number(episode_id: str) -> Optional[int]:
    """Read the sequence from both old ``SY-001`` and new ``SY-n001`` IDs."""
    match = re.match(r"^SY-(?:n)?(\d+)(?:-|$)", str(episode_id), re.IGNORECASE)
    return int(match.group(1)) if match else None


def init_db():
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR, exist_ok=True)
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experiment_runs (
            episode_id TEXT PRIMARY KEY,
            stage TEXT,
            material TEXT,
            thickness_mm REAL,
            gas TEXT,
            power_kw REAL,
            speed_m_min REAL,
            air_pressure_mpa REAL,
            focus_mm REAL,
            A_level INTEGER,
            B_level INTEGER,
            C_level INTEGER,
            D_level INTEGER,
            nozzle_height_mm REAL,
            nozzle_diameter_mm REAL,
            path_type TEXT,
            energy_index REAL,
            cut_through INTEGER,
            failure_case TEXT,
            kerf_width_top_mm REAL,
            kerf_width_bottom_mm REAL,
            taper_mm REAL,
            dross_height_max_mm REAL,
            dross_height_mean_mm REAL,
            roughness_Sa_um REAL,
            defect_area_mm2 REAL,
            manual_comment TEXT,
            quality_score REAL,
            point_cloud_front TEXT,
            point_cloud_back TEXT,
            point_cloud_left TEXT,
            point_cloud_right TEXT,
            point_cloud_top TEXT,
            point_cloud_dross TEXT,
            image_front TEXT,
            image_back TEXT,
            image_left TEXT,
            image_right TEXT,
            image_top TEXT,
            image_bottom TEXT
        );
    """)
    
    # Run migration for existing databases to add new columns if they do not exist
    for col_name in [
        "point_cloud_front", "point_cloud_back", "point_cloud_left", "point_cloud_right", "point_cloud_top", "point_cloud_dross",
        "image_front", "image_back", "image_left", "image_right", "image_top", "image_bottom"
    ]:
        try:
            cursor.execute(f"ALTER TABLE experiment_runs ADD COLUMN {col_name} TEXT;")
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass
            
    conn.commit()
    
    # Check if empty, and import from the original experiment_log.csv if it exists
    cursor.execute("SELECT COUNT(*) FROM experiment_runs;")
    count = cursor.fetchone()[0]
    
    if count == 0:
        src_path = SOURCE_CSV_FILE
        # If original demo is not found, try to see if there's any local CSV
        if not os.path.exists(src_path):
            src_path = os.path.join(DB_DIR, "experiment_log.csv")
            
        if os.path.exists(src_path):
            print(f"[DB] Importing seed data from {src_path}...")
            try:
                df = pd.read_csv(src_path)
                # Handle possible NaN/null values in pandas
                df = df.where(pd.notnull(df), None)
                
                for _, row in df.iterrows():
                    cursor.execute("""
                        INSERT OR REPLACE INTO experiment_runs (
                            episode_id, stage, material, thickness_mm, gas, power_kw, speed_m_min,
                            air_pressure_mpa, focus_mm, A_level, B_level, C_level, D_level,
                            nozzle_height_mm, nozzle_diameter_mm, path_type, energy_index,
                            cut_through, failure_case, kerf_width_top_mm, kerf_width_bottom_mm,
                            taper_mm, dross_height_max_mm, dross_height_mean_mm, roughness_Sa_um,
                            defect_area_mm2, manual_comment, quality_score
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, (
                        row['episode_id'], row['stage'], row['material'], row['thickness_mm'],
                        row['gas'], row['power_kw'], row['speed_m_min'], row['air_pressure_mpa'],
                        row['focus_mm'], row['A_level'], row['B_level'], row['C_level'], row['D_level'],
                        row['nozzle_height_mm'], row['nozzle_diameter_mm'], row['path_type'], row['energy_index'],
                        1 if row['cut_through'] is True or row['cut_through'] == 1 or str(row['cut_through']).lower() == 'true' else 0,
                        row['failure_case'], row['kerf_width_top_mm'], row['kerf_width_bottom_mm'],
                        row['taper_mm'], row['dross_height_max_mm'], row['dross_height_mean_mm'], row['roughness_Sa_um'],
                        row['defect_area_mm2'], row['manual_comment'], row['quality_score']
                    ))
                conn.commit()
                print(f"[DB] Successfully imported {len(df)} records.")
            except Exception as e:
                print(f"[DB] Error importing initial CSV: {e}")
                
    conn.close()
    # Always sync to output folder CSV & JSON on init to guarantee consistency
    sync_data_to_files()

def sync_to_csv():
    """Syncs the database contents back to experiment_log.csv"""
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM experiment_runs", conn)
    conn.close()
    
    # Convert cut_through from 1/0 to True/False for CSV compatibility
    if not df.empty and 'cut_through' in df.columns:
        df['cut_through'] = df['cut_through'].apply(lambda x: True if x == 1 else False)
        
    df.to_csv(CSV_FILE, index=False)
    print(f"[DB] Synced SQLite database to {CSV_FILE}")

def sync_to_json():
    """Syncs the database contents back to experiment_log.json for LLM Agent parsing"""
    import json
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM experiment_runs ORDER BY episode_id DESC;")
    rows = cursor.fetchall()
    conn.close()
    
    runs = []
    for row in rows:
        run_dict = dict(row)
        run_dict['cut_through'] = bool(run_dict['cut_through'])
        runs.append(run_dict)
        
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(runs, f, indent=4, ensure_ascii=False)
    print(f"[DB] Synced SQLite database to {JSON_FILE}")

def sync_data_to_files():
    """Syncs SQLite database to both CSV and JSON formats"""
    sync_to_csv()
    sync_to_json()

def get_all_runs() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM experiment_runs ORDER BY episode_id DESC;")
    rows = cursor.fetchall()
    conn.close()
    
    runs = []
    for row in rows:
        run_dict = dict(row)
        run_dict['cut_through'] = bool(run_dict['cut_through'])
        runs.append(run_dict)
    return runs

def add_run(params: Dict[str, Any]) -> str:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    power = float(params.get('power_kw', 54))
    speed = float(params.get('speed_m_min', 0.8))
    pressure = float(params.get('air_pressure_mpa', 1.5))
    focus = float(params.get('focus_mm', -9))

    # Auto generate episode_id if not present
    episode_id = params.get('episode_id')
    if not episode_id:
        cursor.execute("SELECT episode_id FROM experiment_runs;")
        sequence_numbers = [
            number
            for (existing_id,) in cursor.fetchall()
            if (number := extract_episode_number(existing_id)) is not None
        ]
        next_sequence = max(sequence_numbers, default=0) + 1
        episode_id = build_episode_id(next_sequence, speed, pressure, focus)

    # Calculate energy index: Power / Speed (kW / m/min)
    energy_index = round(power / speed, 3) if speed > 0 else 0.0
    
    cursor.execute("""
        INSERT OR REPLACE INTO experiment_runs (
            episode_id, stage, material, thickness_mm, gas, power_kw, speed_m_min,
            air_pressure_mpa, focus_mm, A_level, B_level, C_level, D_level,
            nozzle_height_mm, nozzle_diameter_mm, path_type, energy_index,
            cut_through, failure_case, kerf_width_top_mm, kerf_width_bottom_mm,
            taper_mm, dross_height_max_mm, dross_height_mean_mm, roughness_Sa_um,
            defect_area_mm2, manual_comment, quality_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        episode_id,
        params.get('stage', 'manual_run'),
        params.get('material', 'carbon_steel'),
        float(params.get('thickness_mm', 30)),
        params.get('gas', 'air'),
        power,
        speed,
        pressure,
        focus,
        params.get('A_level'),
        params.get('B_level'),
        params.get('C_level'),
        params.get('D_level'),
        float(params.get('nozzle_height_mm', 1.0)),
        float(params.get('nozzle_diameter_mm', 4.0)),
        params.get('path_type', 'straight_line'),
        energy_index,
        1 if params.get('cut_through') else 0,
        params.get('failure_case', 'normal'),
        params.get('kerf_width_top_mm'),
        params.get('kerf_width_bottom_mm'),
        params.get('taper_mm'),
        params.get('dross_height_max_mm'),
        params.get('dross_height_mean_mm'),
        params.get('roughness_Sa_um'),
        params.get('defect_area_mm2'),
        params.get('manual_comment', ''),
        params.get('quality_score')
    ))
    
    conn.commit()
    conn.close()
    
    sync_data_to_files()
    return episode_id

def update_run_quality(episode_id: str, quality: Dict[str, Any]):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Calculate score if not provided
    cut_through = quality.get('cut_through', True)
    score = quality.get('quality_score')
    
    if score is None:
        # Standard default scoring logic if user doesn't input one
        if not cut_through:
            score = 30.0
        else:
            # simple formula
            dross = float(quality.get('dross_height_max_mm', 0.0) or 0.0)
            roughness = float(quality.get('roughness_Sa_um', 0.0) or 0.0)
            score = 100.0 - (dross * 15.0) - (roughness * 2.0)
            score = max(0.0, min(100.0, score))
            
    cursor.execute("""
        UPDATE experiment_runs SET
            cut_through = ?,
            failure_case = ?,
            kerf_width_top_mm = ?,
            kerf_width_bottom_mm = ?,
            taper_mm = ?,
            dross_height_max_mm = ?,
            dross_height_mean_mm = ?,
            roughness_Sa_um = ?,
            defect_area_mm2 = ?,
            manual_comment = ?,
            quality_score = ?
        WHERE episode_id = ?;
    """, (
        1 if cut_through else 0,
        quality.get('failure_case', 'normal'),
        quality.get('kerf_width_top_mm'),
        quality.get('kerf_width_bottom_mm'),
        quality.get('taper_mm'),
        quality.get('dross_height_max_mm'),
        quality.get('dross_height_mean_mm'),
        quality.get('roughness_Sa_um'),
        quality.get('defect_area_mm2'),
        quality.get('manual_comment', ''),
        score,
        episode_id
    ))
    
    conn.commit()
    conn.close()
    
    sync_data_to_files()

def delete_run(episode_id: str) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM experiment_runs WHERE episode_id = ?;", (episode_id,))
    deleted = cursor.rowcount > 0
    
    conn.commit()
    conn.close()
    
    if deleted:
        sync_data_to_files()
        
    return deleted

def update_run_parameters(old_episode_id: str, new_episode_id: str, params: Dict[str, Any]) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check if new_episode_id already exists and is different from old_episode_id
    if new_episode_id != old_episode_id:
        cursor.execute("SELECT COUNT(*) FROM experiment_runs WHERE episode_id = ?;", (new_episode_id,))
        if cursor.fetchone()[0] > 0:
            conn.close()
            raise ValueError(f"实验ID/名称 '{new_episode_id}' 已存在，请使用其他名称！")
            
    power = float(params.get('power_kw', 54))
    speed = float(params.get('speed_m_min', 0.8))
    energy_index = round(power / speed, 3) if speed > 0 else 0.0
    
    cursor.execute("""
        UPDATE experiment_runs SET
            episode_id = ?,
            material = ?,
            thickness_mm = ?,
            gas = ?,
            power_kw = ?,
            speed_m_min = ?,
            air_pressure_mpa = ?,
            focus_mm = ?,
            nozzle_height_mm = ?,
            nozzle_diameter_mm = ?,
            energy_index = ?
        WHERE episode_id = ?;
    """, (
        new_episode_id,
        params.get('material', 'carbon_steel'),
        float(params.get('thickness_mm', 30)),
        params.get('gas', 'air'),
        power,
        speed,
        float(params.get('air_pressure_mpa', 1.5)),
        float(params.get('focus_mm', -9)),
        float(params.get('nozzle_height_mm', 1.0)),
        float(params.get('nozzle_diameter_mm', 4.0)),
        energy_index,
        old_episode_id
    ))
    
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    if updated:
        sync_data_to_files()
        
    return updated

def get_last_run_parameters() -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get the last added run (order by rowid desc to get the most recently inserted one)
    cursor.execute("SELECT * FROM experiment_runs ORDER BY rowid DESC LIMIT 1;")
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None

INSPECTION_DIR = os.path.join(DB_DIR, "inspections")

def convert_tif_to_png(tif_path: str, png_path: str):
    """Converts a TIFF file to PNG using PyQt6 QImage (headless)"""
    from PyQt6.QtGui import QImage
    try:
        img = QImage()
        if img.load(tif_path):
            img.save(png_path, "PNG")
            print(f"[IMAGE] Converted {tif_path} to {png_path}")
            return True
        else:
            print(f"[IMAGE] Failed to load TIFF: {tif_path}")
    except Exception as e:
        print(f"[IMAGE] Error converting TIFF {tif_path} to PNG: {e}")
    return False

def save_local_inspection_file(episode_id: str, field_name: str, src_path: str) -> str:
    """Copies a local file to the structured inspections folder and updates DB with relative path"""
    if not src_path or not os.path.exists(src_path):
        return ""
        
    dest_dir = os.path.join(INSPECTION_DIR, episode_id)
    os.makedirs(dest_dir, exist_ok=True)
    
    ext = os.path.splitext(src_path)[1]
    dest_filename = f"{episode_id}_{field_name}{ext}"
    dest_path = os.path.join(dest_dir, dest_filename)
    
    import shutil
    try:
        shutil.copy2(src_path, dest_path)
    except Exception as e:
        print(f"[DB] Error copying file {src_path}: {e}")
        return ""
        
    # Auto-convert TIF to PNG for browser preview support
    if ext.lower() in [".tif", ".tiff"]:
        png_filename = f"{episode_id}_{field_name}.png"
        png_path = os.path.join(dest_dir, png_filename)
        convert_tif_to_png(dest_path, png_path)
    
    # Update SQLite database with relative path
    rel_path = f"data/inspections/{episode_id}/{dest_filename}"
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE experiment_runs SET {field_name} = ? WHERE episode_id = ?;", (rel_path, episode_id))
    conn.commit()
    conn.close()
    
    sync_data_to_files()
    return rel_path

import numpy as np

def parse_point_cloud(file_path: str) -> np.ndarray:
    """
    Parses a 3D point cloud file (.pcd, .asc, .csv, .xyz, .ply) quickly using pandas
    and automatically downsamples large point clouds to at most 20,000 points for stable previewing.
    """
    if not os.path.exists(file_path):
        return np.zeros((0, 3), dtype=np.float32)
        
    ext = os.path.splitext(file_path)[1].lower()
    points = None
    
    try:
        if ext in {".pcd", ".ply"}:
            declared_count = 0
            count_prefix = "POINTS" if ext == ".pcd" else "element vertex"
            terminator = "DATA ascii" if ext == ".pcd" else "end_header"
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.lower().startswith(count_prefix.lower()):
                        try:
                            declared_count = int(stripped.split()[-1])
                        except ValueError:
                            pass
                    if stripped.lower() == terminator.lower():
                        break

            max_preview_points = 20_000
            step = max(1, declared_count // max_preview_points)
            sampled_chunks = []
            offset = 0
            for chunk in iter_point_cloud_chunks(file_path):
                if step > 1:
                    indices = np.arange(len(chunk), dtype=np.int64) + offset
                    sampled = chunk[(indices % step) == 0]
                else:
                    sampled = chunk
                if len(sampled):
                    sampled_chunks.append(sampled)
                offset += len(chunk)
            points = (
                np.concatenate(sampled_chunks)[:max_preview_points]
                if sampled_chunks
                else np.zeros((0, 3), dtype=np.float32)
            )
            if declared_count > max_preview_points:
                print(
                    f"[PCD] Stream-sampled large point cloud from "
                    f"{declared_count:,} to {len(points):,} preview points."
                )
            
        else:
            # ASC / CSV / XYZ
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                first_line = f.readline()
                
            delim = None
            for d in [",", ";", "\t"]:
                if d in first_line:
                    delim = d
                    break
            
            sep = delim if delim else r"\s+"
            
            has_header = any(c.isalpha() for c in first_line.replace(",", "").replace(" ", "").strip())
            header_val = 0 if has_header else None
            
            df = pd.read_csv(file_path, sep=sep, header=header_val, usecols=[0, 1, 2], dtype=np.float32)
            points = df.to_numpy()
            
    except Exception as e:
        print(f"[DB] Error parsing point cloud {file_path} via pandas: {e}")
        # Fallback to standard line-by-line parsing if pandas fails
        points = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                header_ended = (ext != ".pcd" and ext != ".ply")
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if not header_ended:
                        if ext == ".pcd" and line.startswith("DATA ascii"):
                            header_ended = True
                        elif ext == ".ply" and line == "end_header":
                            header_ended = True
                        continue
                    
                    parts = line.replace(",", " ").replace(";", " ").replace("\t", " ").split()
                    if len(parts) >= 3:
                        try:
                            points.append([float(parts[0]), float(parts[1]), float(parts[2])])
                        except ValueError:
                            pass
            points = np.array(points, dtype=np.float32)
        except Exception as fallback_err:
            print(f"[DB] Fallback parser failed: {fallback_err}")
            points = np.zeros((0, 3), dtype=np.float32)

    if points is None or len(points) == 0:
        return np.zeros((0, 3), dtype=np.float32)

    # AUTO DOWNSAMPLE: Limit points to at most 20,000
    max_preview_points = 20000
    n = len(points)
    if n > max_preview_points:
        step = n // max_preview_points
        points = points[::step][:max_preview_points]
        print(f"[PCD] Auto-downsampled large point cloud from {n:,} to {len(points):,} points.")
        
    return points

def iter_point_cloud_chunks(file_path: str, chunk_size: int = 500_000):
    """Yield full-resolution XYZ chunks without loading the entire file."""
    ext = os.path.splitext(file_path)[1].lower()
    skip_rows = 0
    separator = r"\s+"
    engine = "c"

    if ext in {".pcd", ".ply"}:
        terminator = "DATA ascii" if ext == ".pcd" else "end_header"
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                skip_rows += 1
                if line.strip().lower() == terminator.lower():
                    break
        if skip_rows == 0:
            raise ValueError(f"无法识别点云文件头: {file_path}")
    else:
        separator = r"[\s,;\t]+"
        engine = "python"

    reader = pd.read_csv(
        file_path,
        skiprows=skip_rows,
        sep=separator,
        engine=engine,
        header=None,
        usecols=[0, 1, 2],
        chunksize=chunk_size,
        on_bad_lines="skip",
    )
    for chunk in reader:
        numeric = chunk.apply(pd.to_numeric, errors="coerce").dropna()
        if not numeric.empty:
            yield numeric.to_numpy(dtype=np.float32, copy=False)

def extract_full_resolution_surface(
    file_path: str,
    preview_points: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Extract the original-resolution center surface in a memory-safe second pass.

    The lightweight preview determines the X/Y ROI and surface-height model.
    The source file is then streamed in chunks, retaining every original point
    that belongs to that surface layer.
    """
    if preview_points is None or len(preview_points) < 100:
        preview_points = parse_point_cloud(file_path)
    if len(preview_points) < 100:
        raise ValueError("预览点不足，无法确定原始切面范围")

    preview_roi = extract_adaptive_core_region(preview_points)
    preview_surface = extract_connected_surface_layer(preview_roi)
    if len(preview_surface) < 30:
        raise ValueError("未能从预览点云中识别稳定的中心切面")

    xy_min = np.min(preview_roi[:, :2], axis=0)
    xy_max = np.max(preview_roi[:, :2], axis=0)
    preview_analysis = analyze_surface_morphology(preview_surface)
    plane = preview_analysis["reference_plane"]
    coeffs = np.asarray([plane["a"], plane["b"], plane["c"]], dtype=np.float64)
    preview_residual = preview_surface[:, 2] - (
        coeffs[0] * preview_surface[:, 0]
        + coeffs[1] * preview_surface[:, 1]
        + coeffs[2]
    )
    residual_center = float(np.median(preview_residual))
    residual_mad = float(
        np.median(np.abs(preview_residual - residual_center)) * 1.4826
    )
    margin = max(0.15, 3.0 * residual_mad)
    residual_low = float(np.percentile(preview_residual, 0.1) - margin)
    residual_high = float(np.percentile(preview_residual, 99.9) + margin)

    surface_chunks = []
    source_count = 0
    roi_count = 0
    for chunk in iter_point_cloud_chunks(file_path):
        source_count += len(chunk)
        roi_mask = (
            (chunk[:, 0] >= xy_min[0])
            & (chunk[:, 0] <= xy_max[0])
            & (chunk[:, 1] >= xy_min[1])
            & (chunk[:, 1] <= xy_max[1])
        )
        roi_chunk = chunk[roi_mask]
        roi_count += len(roi_chunk)
        if len(roi_chunk) == 0:
            continue
        residual = roi_chunk[:, 2] - (
            coeffs[0] * roi_chunk[:, 0]
            + coeffs[1] * roi_chunk[:, 1]
            + coeffs[2]
        )
        layer_mask = (residual >= residual_low) & (residual <= residual_high)
        if np.any(layer_mask):
            surface_chunks.append(roi_chunk[layer_mask])

    if not surface_chunks:
        raise ValueError("原始点云中没有找到与预览切面匹配的高度层")
    surface = np.concatenate(surface_chunks).astype(np.float32, copy=False)
    return {
        "surface_points": surface,
        "source_point_count": int(source_count),
        "roi_point_count": int(roi_count),
        "surface_point_count": int(len(surface)),
        "preview_surface_point_count": int(len(preview_surface)),
        "xy_bounds": {
            "x_min": float(xy_min[0]),
            "x_max": float(xy_max[0]),
            "y_min": float(xy_min[1]),
            "y_max": float(xy_max[1]),
        },
        "residual_band_mm": {
            "low": residual_low,
            "high": residual_high,
        },
    }

def denoise_point_cloud(pts: np.ndarray) -> np.ndarray:
    """Filter outlier points that lie more than 3 standard deviations from the mean coordinate components"""
    if len(pts) < 10:
        return pts
    mean = np.mean(pts, axis=0)
    std = np.std(pts, axis=0)
    std = np.where(std == 0.0, 1.0, std)
    mask = np.all(np.abs(pts - mean) < 3.0 * std, axis=1)
    return pts[mask]

def downsample_point_cloud(pts: np.ndarray, target_count: int = 5000) -> np.ndarray:
    """Downsample point cloud to target number of points by step slicing"""
    n = len(pts)
    if n <= target_count:
        return pts
    step = n // target_count
    return pts[::step][:target_count]

def save_point_cloud_data(file_path: str, points: np.ndarray) -> bool:
    """Saves numpy array of points back to file in PCD, PLY, CSV or ASC format."""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".pcd":
            # Write PCD ASCII format
            n = len(points)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("# .PCD v0.7 - Point Cloud Data file format\n")
                f.write("VERSION 0.7\n")
                f.write("FIELDS x y z\n")
                f.write("SIZE 4 4 4\n")
                f.write("TYPE F F F\n")
                f.write("COUNT 1 1 1\n")
                f.write(f"WIDTH {n}\n")
                f.write("HEIGHT 1\n")
                f.write("VIEWPOINT 0 0 0 1 0 0 0\n")
                f.write(f"POINTS {n}\n")
                f.write("DATA ascii\n")
                for pt in points:
                    f.write(f"{pt[0]:.6f} {pt[1]:.6f} {pt[2]:.6f}\n")
            return True
            
        elif ext == ".csv":
            # Write CSV format
            df = pd.DataFrame(points, columns=["x", "y", "z"])
            df.to_csv(file_path, index=False, header=False)
            return True
            
        else:
            # ASC / PLY / XYZ / TXT: write space-separated coordinates
            with open(file_path, "w", encoding="utf-8") as f:
                for pt in points:
                    f.write(f"{pt[0]:.6f} {pt[1]:.6f} {pt[2]:.6f}\n")
            return True
    except Exception as e:
        print(f"[DB] Error saving point cloud back to {file_path}: {e}")
        return False

def extract_core_region(pts: np.ndarray, keep_ratio: float = 0.5) -> np.ndarray:
    """
    Extract the centered region of a section point cloud.

    Cropping is applied to the X/Y section plane while the full Z depth is
    retained, so surface-height information is not discarded.
    """
    if pts is None or len(pts) == 0:
        return np.zeros((0, 3), dtype=np.float32)
    if pts.ndim != 2 or pts.shape[1] < 3:
        raise ValueError("点云数据必须是包含 X、Y、Z 的二维数组")
    if not 0.0 < keep_ratio <= 1.0:
        raise ValueError("核心区域保留比例必须在 0 到 1 之间")

    xy = pts[:, :2]
    xy_min = np.min(xy, axis=0)
    xy_max = np.max(xy, axis=0)
    center = (xy_min + xy_max) / 2.0
    half_size = (xy_max - xy_min) * keep_ratio / 2.0
    lower = center - half_size
    upper = center + half_size
    mask = np.all((xy >= lower) & (xy <= upper), axis=1)
    return pts[mask].copy()

def _extract_density_core_region(pts: np.ndarray, bins: int = 64) -> np.ndarray:
    """
    Detect a centered, high-density section region in the X/Y projection.

    Each axis is converted to a smoothed density profile. Starting from the
    strongest bin near the geometric center, the algorithm expands through
    the contiguous dense interval and combines the detected X/Y bounds.
    Z is deliberately not cropped.
    """
    if pts is None or len(pts) == 0:
        return np.zeros((0, 3), dtype=np.float32)
    if pts.ndim != 2 or pts.shape[1] < 3:
        raise ValueError("点云数据必须是包含 X、Y、Z 的二维数组")

    finite_pts = pts[np.all(np.isfinite(pts[:, :3]), axis=1)]
    if len(finite_pts) < 30:
        return finite_pts.copy()

    bounds = []
    bins = max(16, min(int(bins), 256))
    for axis in (0, 1):
        values = finite_pts[:, axis]
        robust_min, robust_max = np.percentile(values, [0.5, 99.5])
        if robust_max <= robust_min:
            bounds.append((robust_min, robust_max))
            continue

        hist, edges = np.histogram(values, bins=bins, range=(robust_min, robust_max))
        smooth = np.convolve(hist.astype(float), np.ones(5) / 5.0, mode="same")

        center_idx = bins // 2
        search_radius = max(2, bins // 6)
        search_start = max(0, center_idx - search_radius)
        search_end = min(bins, center_idx + search_radius + 1)
        seed_idx = search_start + int(np.argmax(smooth[search_start:search_end]))
        seed_density = smooth[seed_idx]

        positive = smooth[smooth > 0]
        if seed_density <= 0 or len(positive) == 0:
            bounds.append((robust_min, robust_max))
            continue

        density_floor = float(np.percentile(positive, 50))
        threshold = min(max(seed_density * 0.25, density_floor), seed_density * 0.8)

        left = seed_idx
        right = seed_idx
        while left > 0 and smooth[left - 1] >= threshold:
            left -= 1
        while right < bins - 1 and smooth[right + 1] >= threshold:
            right += 1

        # Include one boundary bin to avoid cutting points on the detected edge.
        left = max(0, left - 1)
        right = min(bins - 1, right + 1)
        bounds.append((edges[left], edges[right + 1]))

    mask = (
        (finite_pts[:, 0] >= bounds[0][0])
        & (finite_pts[:, 0] <= bounds[0][1])
        & (finite_pts[:, 1] >= bounds[1][0])
        & (finite_pts[:, 1] <= bounds[1][1])
    )
    core = finite_pts[mask]

    # Sparse or fragmented clouds can make density detection too restrictive.
    # Fall back to a robust centered box instead of returning an unusable ROI.
    if len(core) < max(10, int(len(finite_pts) * 0.05)):
        xy_min = np.percentile(finite_pts[:, :2], 20, axis=0)
        xy_max = np.percentile(finite_pts[:, :2], 80, axis=0)
        fallback_mask = np.all(
            (finite_pts[:, :2] >= xy_min) & (finite_pts[:, :2] <= xy_max),
            axis=1,
        )
        core = finite_pts[fallback_mask]

    return core.copy()

def extract_adaptive_core_region(pts: np.ndarray, bins: int = 64) -> np.ndarray:
    """
    Extract the centered section by its height difference from the background.

    A robust plane is fitted to the outer frame of the cloud first. The
    residual height profiles along X and Y are then used to find the
    contiguous elevated or recessed interval around the center. Density-based
    extraction is retained as a fallback for clouds without a clear height
    contrast.
    """
    if pts is None or len(pts) == 0:
        return np.zeros((0, 3), dtype=np.float32)
    if pts.ndim != 2 or pts.shape[1] < 3:
        raise ValueError("点云数据必须是包含 X、Y、Z 的二维数组")

    finite_pts = pts[np.all(np.isfinite(pts[:, :3]), axis=1)]
    if len(finite_pts) < 100:
        return finite_pts.copy()

    bins = max(24, min(int(bins), 256))
    xy = finite_pts[:, :2].astype(np.float64)
    z = finite_pts[:, 2].astype(np.float64)
    xy_min = np.percentile(xy, 0.5, axis=0)
    xy_max = np.percentile(xy, 99.5, axis=0)
    xy_range = xy_max - xy_min
    if np.any(xy_range <= 0):
        return _extract_density_core_region(finite_pts, bins)

    normalized = (xy - xy_min) / xy_range
    outer_mask = np.any((normalized <= 0.15) | (normalized >= 0.85), axis=1)
    if np.count_nonzero(outer_mask) < 30:
        return _extract_density_core_region(finite_pts, bins)

    # Robustly fit z = ax + by + c to the outer frame.
    outer_xy = xy[outer_mask]
    outer_z = z[outer_mask]
    design = np.column_stack((outer_xy, np.ones(len(outer_xy))))
    coeffs, *_ = np.linalg.lstsq(design, outer_z, rcond=None)
    for _ in range(2):
        fit_error = outer_z - design @ coeffs
        error_center = np.median(fit_error)
        error_mad = np.median(np.abs(fit_error - error_center))
        if error_mad <= 1e-9:
            break
        inliers = np.abs(fit_error - error_center) <= 3.5 * 1.4826 * error_mad
        if np.count_nonzero(inliers) < 30:
            break
        coeffs, *_ = np.linalg.lstsq(design[inliers], outer_z[inliers], rcond=None)

    residual = z - (
        coeffs[0] * xy[:, 0] + coeffs[1] * xy[:, 1] + coeffs[2]
    )
    outer_residual = residual[outer_mask]
    background_center = float(np.median(outer_residual))
    background_mad = float(
        np.median(np.abs(outer_residual - background_center)) * 1.4826
    )
    residual -= background_center

    center_mask = np.all((normalized >= 0.38) & (normalized <= 0.62), axis=1)
    if np.count_nonzero(center_mask) < 10:
        return _extract_density_core_region(finite_pts, bins)
    center_height = float(np.median(residual[center_mask]))
    min_contrast = max(background_mad * 6.0, 0.05)
    if abs(center_height) < min_contrast:
        return _extract_density_core_region(finite_pts, bins)

    direction = 1.0 if center_height >= 0 else -1.0
    signed_height = direction * residual
    clip_low, clip_high = np.percentile(signed_height, [1, 99])
    signed_height = np.clip(signed_height, clip_low, clip_high)

    detected_bounds = []
    for axis in (0, 1):
        indices = np.floor(normalized[:, axis] * bins).astype(int)
        indices = np.clip(indices, 0, bins - 1)
        sums = np.bincount(indices, weights=signed_height, minlength=bins)
        counts = np.bincount(indices, minlength=bins)
        profile = np.divide(
            sums,
            counts,
            out=np.zeros(bins, dtype=float),
            where=counts > 0,
        )
        profile = np.convolve(profile, np.ones(3) / 3.0, mode="same")

        center_idx = bins // 2
        search_radius = max(2, bins // 6)
        start = max(0, center_idx - search_radius)
        end = min(bins, center_idx + search_radius + 1)
        seed = start + int(np.argmax(profile[start:end]))
        seed_height = float(profile[seed])
        threshold = max(background_mad * 4.0, seed_height * 0.40)
        if seed_height <= threshold:
            return _extract_density_core_region(finite_pts, bins)

        left = seed
        right = seed
        while left > 0 and profile[left - 1] >= threshold:
            left -= 1
        while right < bins - 1 and profile[right + 1] >= threshold:
            right += 1

        bin_width = xy_range[axis] / bins
        detected_bounds.append(
            (
                xy_min[axis] + left * bin_width,
                xy_min[axis] + (right + 1) * bin_width,
            )
        )

    core_mask = (
        (xy[:, 0] >= detected_bounds[0][0])
        & (xy[:, 0] <= detected_bounds[0][1])
        & (xy[:, 1] >= detected_bounds[1][0])
        & (xy[:, 1] <= detected_bounds[1][1])
    )
    core = finite_pts[core_mask]
    if len(core) < max(10, int(len(finite_pts) * 0.01)):
        return _extract_density_core_region(finite_pts, bins)
    return core.copy()

def _remove_floating_spikes_local(
    pts: np.ndarray,
    sigma_threshold: float = 8.0,
    min_height_mm: float = 0.5,
) -> np.ndarray:
    """
    Remove isolated points floating above their local X/Y neighborhood.

    Only positive Z outliers are removed. The cutoff is the larger of an
    absolute height threshold and a robust MAD-based noise threshold, which
    preserves normal surface texture and recessed defects.
    """
    if pts is None or len(pts) == 0:
        return np.zeros((0, 3), dtype=np.float32)
    if pts.ndim != 2 or pts.shape[1] < 3:
        raise ValueError("点云数据必须是包含 X、Y、Z 的二维数组")
    if len(pts) < 20:
        return pts.copy()

    finite_mask = np.all(np.isfinite(pts[:, :3]), axis=1)
    finite_pts = pts[finite_mask]
    if len(finite_pts) < 20:
        return finite_pts.copy()

    xy = finite_pts[:, :2].astype(np.float64)
    xy_min = np.min(xy, axis=0)
    xy_span = np.max(xy, axis=0) - xy_min
    max_span = float(np.max(xy_span))
    if max_span <= 0:
        return finite_pts.copy()

    # Aim for roughly eight points per cell before collecting a 3x3
    # neighborhood. Aspect-aware dimensions also support rectangular cuts.
    target = max(4, int(np.sqrt(len(finite_pts) / 8.0)))
    grid_x = max(4, int(round(target * xy_span[0] / max_span)))
    grid_y = max(4, int(round(target * xy_span[1] / max_span)))
    x_index = np.clip(
        ((xy[:, 0] - xy_min[0]) / max(xy_span[0], 1e-9) * grid_x).astype(int),
        0,
        grid_x - 1,
    )
    y_index = np.clip(
        ((xy[:, 1] - xy_min[1]) / max(xy_span[1], 1e-9) * grid_y).astype(int),
        0,
        grid_y - 1,
    )

    cells: Dict[tuple, List[int]] = {}
    for index, key in enumerate(zip(x_index, y_index)):
        cells.setdefault(key, []).append(index)

    local_median = finite_pts[:, 2].astype(np.float64).copy()
    for key, indices in cells.items():
        neighbor_indices = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                neighbor_indices.extend(cells.get((key[0] + dx, key[1] + dy), []))
        if len(neighbor_indices) >= 6:
            local_median[indices] = np.median(finite_pts[neighbor_indices, 2])

    residual = finite_pts[:, 2] - local_median
    residual_center = float(np.median(residual))
    noise_mad = float(
        np.median(np.abs(residual - residual_center)) * 1.4826
    )
    cutoff = max(float(min_height_mm), float(sigma_threshold) * noise_mad)
    keep = residual <= cutoff
    return finite_pts[keep].copy()

def extract_connected_surface_layer(pts: np.ndarray) -> np.ndarray:
    """
    Keep the center-seeded, height-continuous surface layer.

    The cloud is divided into an X/Y grid. Region growing starts from the
    center surface and only enters neighboring cells with continuous median
    height. Points outside the connected layer, below the surface, or floating
    above their cell are removed. Original coordinates are never modified.
    """
    if pts is None or len(pts) == 0:
        return np.zeros((0, 3), dtype=np.float32)
    if pts.ndim != 2 or pts.shape[1] < 3:
        raise ValueError("点云数据必须是包含 X、Y、Z 的二维数组")
    if len(pts) < 30:
        return pts.copy()

    finite_pts = pts[np.all(np.isfinite(pts[:, :3]), axis=1)]
    if len(finite_pts) < 30:
        return finite_pts.copy()

    xy = finite_pts[:, :2].astype(np.float64)
    z = finite_pts[:, 2].astype(np.float64)
    xy_min = np.min(xy, axis=0)
    xy_span = np.max(xy, axis=0) - xy_min
    max_span = float(np.max(xy_span))
    if max_span <= 0:
        return _remove_floating_spikes_local(finite_pts)

    normalized = (xy - xy_min) / np.maximum(xy_span, 1e-9)
    center_mask = np.all((normalized >= 0.35) & (normalized <= 0.65), axis=1)
    if np.count_nonzero(center_mask) < 10:
        return _remove_floating_spikes_local(finite_pts)

    center_height = float(np.median(z[center_mask]))
    center_mad = float(
        np.median(np.abs(z[center_mask] - center_height)) * 1.4826
    )
    neighbor_tolerance = max(0.6, 8.0 * center_mad)
    layer_tolerance = max(1.2, 12.0 * center_mad)
    point_tolerance = max(0.5, 8.0 * center_mad)

    target = max(6, int(np.sqrt(len(finite_pts) / 4.0)))
    grid_x = max(6, int(round(target * xy_span[0] / max_span)))
    grid_y = max(6, int(round(target * xy_span[1] / max_span)))
    x_index = np.clip((normalized[:, 0] * grid_x).astype(int), 0, grid_x - 1)
    y_index = np.clip((normalized[:, 1] * grid_y).astype(int), 0, grid_y - 1)

    cells: Dict[tuple, List[int]] = {}
    for index, key in enumerate(zip(x_index, y_index)):
        cells.setdefault(key, []).append(index)
    cell_height = {
        key: float(np.median(z[indices]))
        for key, indices in cells.items()
    }

    central_cells = [
        key
        for key in cells
        if 0.30 <= (key[0] + 0.5) / grid_x <= 0.70
        and 0.30 <= (key[1] + 0.5) / grid_y <= 0.70
    ]
    if not central_cells:
        return _remove_floating_spikes_local(finite_pts)

    seed = min(
        central_cells,
        key=lambda key: (
            abs(cell_height[key] - center_height)
            + 0.02
            * (
                (key[0] + 0.5 - grid_x / 2.0) ** 2
                + (key[1] + 0.5 - grid_y / 2.0) ** 2
            )
        ),
    )

    selected_cells = {seed}
    queue = [seed]
    queue_index = 0
    while queue_index < len(queue):
        key = queue[queue_index]
        queue_index += 1
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                neighbor = (key[0] + dx, key[1] + dy)
                if neighbor not in cells or neighbor in selected_cells:
                    continue
                if (
                    abs(cell_height[neighbor] - cell_height[key])
                    <= neighbor_tolerance
                    and abs(cell_height[neighbor] - center_height)
                    <= layer_tolerance
                ):
                    selected_cells.add(neighbor)
                    queue.append(neighbor)

    keep = np.zeros(len(finite_pts), dtype=bool)
    for key in selected_cells:
        indices = np.asarray(cells[key], dtype=int)
        keep[indices] = (
            (np.abs(z[indices] - cell_height[key]) <= point_tolerance)
            & (np.abs(z[indices] - center_height) <= layer_tolerance)
        )

    surface = finite_pts[keep]
    if len(surface) < max(20, int(len(finite_pts) * 0.10)):
        return _remove_floating_spikes_local(finite_pts)
    return surface.copy()

def remove_floating_spikes(
    pts: np.ndarray,
    sigma_threshold: float = 8.0,
    min_height_mm: float = 0.5,
) -> np.ndarray:
    """Backward-compatible entry point for connected surface extraction."""
    return extract_connected_surface_layer(pts)

def analyze_surface_morphology(pts: np.ndarray) -> Dict[str, Any]:
    """
    Calculate extensible areal surface-morphology metrics.

    A robust least-squares plane is removed as the reference form. The
    original point coordinates are not changed. Values are suitable for
    comparative process analysis; ISO-certified roughness requires calibrated
    sampling and the specified S/L filters.
    """
    if pts is None or len(pts) < 3:
        raise ValueError("至少需要 3 个有效切面点才能计算形貌")
    if pts.ndim != 2 or pts.shape[1] < 3:
        raise ValueError("点云数据必须是包含 X、Y、Z 的二维数组")

    finite_pts = pts[np.all(np.isfinite(pts[:, :3]), axis=1)]
    if len(finite_pts) < 3:
        raise ValueError("有效切面点不足，无法计算形貌")

    xyz = finite_pts[:, :3].astype(np.float64)
    design = np.column_stack((xyz[:, 0], xyz[:, 1], np.ones(len(xyz))))
    z = xyz[:, 2]
    inliers = np.ones(len(xyz), dtype=bool)
    coeffs = np.zeros(3, dtype=float)
    for _ in range(3):
        coeffs, *_ = np.linalg.lstsq(design[inliers], z[inliers], rcond=None)
        fit_residual = z - design @ coeffs
        center = float(np.median(fit_residual[inliers]))
        mad = float(
            np.median(np.abs(fit_residual[inliers] - center)) * 1.4826
        )
        if mad <= 1e-12:
            break
        next_inliers = np.abs(fit_residual - center) <= 4.0 * mad
        if np.count_nonzero(next_inliers) < 3 or np.array_equal(next_inliers, inliers):
            break
        inliers = next_inliers

    residual_mm = z - design @ coeffs
    residual_mm -= np.median(residual_mm)
    residual_um = residual_mm * 1000.0
    sq = float(np.sqrt(np.mean(residual_um ** 2)))
    sa = float(np.mean(np.abs(residual_um)))
    sp = float(np.max(residual_um))
    sv = float(abs(np.min(residual_um)))
    sz = sp + sv
    if sq > 1e-12:
        ssk = float(np.mean(residual_um ** 3) / (sq ** 3))
        sku = float(np.mean(residual_um ** 4) / (sq ** 4))
    else:
        ssk = 0.0
        sku = 0.0

    xy_min = np.min(xyz[:, :2], axis=0)
    xy_max = np.max(xyz[:, :2], axis=0)
    width, height = xy_max - xy_min
    projected_area = float(width * height)
    robust_height = float(
        np.percentile(residual_um, 95) - np.percentile(residual_um, 5)
    )
    slope_x_deg = float(np.degrees(np.arctan(coeffs[0])))
    slope_y_deg = float(np.degrees(np.arctan(coeffs[1])))

    def metric(
        key: str,
        label: str,
        value: float,
        unit: str,
        description: str,
    ) -> Dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "value": round(float(value), 4),
            "unit": unit,
            "description": description,
        }

    metrics = [
        metric("Sa", "算术平均高度 Sa", sa, "µm", "基准面残差绝对值的平均值"),
        metric("Sq", "均方根高度 Sq", sq, "µm", "基准面残差的均方根"),
        metric("Sz", "最大高度 Sz", sz, "µm", "最高峰 Sp 与最深谷 Sv 之和"),
        metric("Sp", "最大峰高 Sp", sp, "µm", "基准面以上的最大高度"),
        metric("Sv", "最大谷深 Sv", sv, "µm", "基准面以下的最大深度"),
        metric("Ssk", "偏斜度 Ssk", ssk, "", "高度分布的不对称程度"),
        metric("Sku", "峭度 Sku", sku, "", "高度分布的尖锐程度"),
        metric(
            "height_p95_p5",
            "稳健高度范围 P95–P5",
            robust_height,
            "µm",
            "排除两端各 5% 极值后的高度范围",
        ),
        metric("width", "有效宽度", width, "mm", "参与计算点云的 X 向范围"),
        metric("height", "有效高度", height, "mm", "参与计算点云的 Y 向范围"),
        metric(
            "point_density",
            "投影点密度",
            len(xyz) / projected_area if projected_area > 0 else 0.0,
            "点/mm²",
            "有效点数除以 X/Y 包围面积",
        ),
    ]
    return {
        "point_count": int(len(xyz)),
        "reference_plane": {
            "a": round(float(coeffs[0]), 8),
            "b": round(float(coeffs[1]), 8),
            "c": round(float(coeffs[2]), 8),
            "slope_x_deg": round(slope_x_deg, 6),
            "slope_y_deg": round(slope_y_deg, 6),
            "fit_inlier_count": int(np.count_nonzero(inliers)),
        },
        "metrics": metrics,
        "note": "已去除稳健基准平面；未进行 ISO 25178 规定的 S/L 截止波长滤波，当前结果适用于工艺对比。",
    }


def detect_surface_protrusions(
    pts: np.ndarray,
    min_height_mm: Optional[float] = None,
    grid_cell_mm: float = 0.25,
    min_area_mm2: float = 0.50,
    merge_gap_mm: float = 0.50,
    max_regions: int = 20,
) -> Dict[str, Any]:
    """Detect connected positive-height protrusions on an extracted surface.

    The detector removes a robust reference plane, derives a height threshold
    from the residual noise, and groups the high points in an X/Y occupancy
    grid.  Returned boxes contain both millimetre coordinates and coordinates
    normalized to the extracted workpiece surface.
    """
    if pts is None or len(pts) < 30:
        raise ValueError("至少需要 30 个切面点才能识别挂渣凸起")
    if pts.ndim != 2 or pts.shape[1] < 3:
        raise ValueError("点云数据必须是包含 X、Y、Z 的二维数组")

    xyz = pts[np.all(np.isfinite(pts[:, :3]), axis=1), :3].astype(
        np.float64,
        copy=False,
    )
    if len(xyz) < 30:
        raise ValueError("有效切面点不足，无法识别挂渣凸起")

    # Robustly fit the nominal workpiece plane. Positive residuals are the
    # physical protrusions visible on the upper surface scan.
    design = np.column_stack((xyz[:, 0], xyz[:, 1], np.ones(len(xyz))))
    z = xyz[:, 2]
    inliers = np.ones(len(xyz), dtype=bool)
    coeffs = np.zeros(3, dtype=np.float64)
    for _ in range(4):
        coeffs, *_ = np.linalg.lstsq(design[inliers], z[inliers], rcond=None)
        fit_residual = z - design @ coeffs
        center = float(np.median(fit_residual[inliers]))
        sigma = float(
            1.4826 * np.median(np.abs(fit_residual[inliers] - center))
        )
        if sigma <= 1e-12:
            break
        next_inliers = np.abs(fit_residual - center) <= 4.0 * sigma
        if np.count_nonzero(next_inliers) < 30 or np.array_equal(
            next_inliers,
            inliers,
        ):
            break
        inliers = next_inliers

    residual = z - design @ coeffs
    residual_center = float(np.median(residual))
    residual -= residual_center
    noise_sigma = float(1.4826 * np.median(np.abs(residual)))
    adaptive_threshold = max(0.05, 6.0 * noise_sigma)
    if min_height_mm is not None:
        adaptive_threshold = max(float(min_height_mm), adaptive_threshold)
    # Prevent a very rough surface from making the detector completely blind.
    adaptive_threshold = min(adaptive_threshold, 0.30)

    xy_min = np.min(xyz[:, :2], axis=0)
    xy_max = np.max(xyz[:, :2], axis=0)
    xy_span = xy_max - xy_min
    if np.any(xy_span <= 1e-9):
        raise ValueError("切面 X/Y 范围无效，无法建立挂渣区域")

    defect_mask = residual >= adaptive_threshold
    defect_indices = np.flatnonzero(defect_mask)
    result: Dict[str, Any] = {
        "threshold_mm": round(float(adaptive_threshold), 6),
        "noise_sigma_mm": round(float(noise_sigma), 6),
        "residual_center_mm": float(residual_center),
        "reference_plane": {
            "a": round(float(coeffs[0]), 8),
            "b": round(float(coeffs[1]), 8),
            "c": round(float(coeffs[2]), 8),
        },
        "surface_bounds_mm": {
            "x_min": float(xy_min[0]),
            "x_max": float(xy_max[0]),
            "y_min": float(xy_min[1]),
            "y_max": float(xy_max[1]),
        },
        "candidate_point_count": int(len(defect_indices)),
        "regions": [],
    }
    if len(defect_indices) == 0:
        return result

    cell = max(0.05, float(grid_cell_mm))
    grid_w = int(np.floor(xy_span[0] / cell)) + 1
    grid_h = int(np.floor(xy_span[1] / cell)) + 1
    defect_xy = xyz[defect_indices, :2]
    gx = np.clip(
        np.floor((defect_xy[:, 0] - xy_min[0]) / cell).astype(np.int32),
        0,
        grid_w - 1,
    )
    gy = np.clip(
        np.floor((defect_xy[:, 1] - xy_min[1]) / cell).astype(np.int32),
        0,
        grid_h - 1,
    )
    flat_cell = gy.astype(np.int64) * grid_w + gx
    cell_counts = np.bincount(flat_cell, minlength=grid_w * grid_h).reshape(
        grid_h,
        grid_w,
    )
    occupied = cell_counts >= 2

    # Bridge sub-millimetre holes so one physical dross patch is not returned
    # as dozens of boxes. Bounding boxes are later measured from real points,
    # not from this expanded grid.
    radius = max(0, int(np.ceil(float(merge_gap_mm) / cell)))
    expanded = occupied.copy()
    if radius:
        source = occupied
        for dy in range(-radius, radius + 1):
            y_src0 = max(0, -dy)
            y_src1 = min(grid_h, grid_h - dy)
            y_dst0 = max(0, dy)
            y_dst1 = min(grid_h, grid_h + dy)
            for dx in range(-radius, radius + 1):
                x_src0 = max(0, -dx)
                x_src1 = min(grid_w, grid_w - dx)
                x_dst0 = max(0, dx)
                x_dst1 = min(grid_w, grid_w + dx)
                expanded[y_dst0:y_dst1, x_dst0:x_dst1] |= source[
                    y_src0:y_src1,
                    x_src0:x_src1,
                ]

    labels = np.zeros((grid_h, grid_w), dtype=np.int32)
    pending = {tuple(v) for v in np.argwhere(expanded)}
    label = 0
    while pending:
        label += 1
        seed = pending.pop()
        labels[seed] = label
        queue = [seed]
        for cy, cx in queue:
            for ny in range(max(0, cy - 1), min(grid_h, cy + 2)):
                for nx in range(max(0, cx - 1), min(grid_w, cx + 2)):
                    neighbor = (ny, nx)
                    if neighbor in pending:
                        pending.remove(neighbor)
                        labels[ny, nx] = label
                        queue.append(neighbor)

    point_labels = labels[gy, gx]
    regions = []
    pad_mm = max(cell, 0.25)
    for component_id in range(1, label + 1):
        local = point_labels == component_id
        point_count = int(np.count_nonzero(local))
        if point_count < 12:
            continue
        component_cells = np.unique(flat_cell[local])
        area_mm2 = float(len(component_cells) * cell * cell)
        if area_mm2 < float(min_area_mm2):
            continue

        component_points = defect_xy[local]
        component_residual = residual[defect_indices[local]]
        lo = np.maximum(np.min(component_points, axis=0) - pad_mm, xy_min)
        hi = np.minimum(np.max(component_points, axis=0) + pad_mm, xy_max)
        normalized = np.array(
            [
                (lo[0] - xy_min[0]) / xy_span[0],
                (lo[1] - xy_min[1]) / xy_span[1],
                (hi[0] - xy_min[0]) / xy_span[0],
                (hi[1] - xy_min[1]) / xy_span[1],
            ],
            dtype=float,
        )
        normalized = np.clip(normalized, 0.0, 1.0)
        regions.append(
            {
                "point_count": point_count,
                "area_mm2": round(area_mm2, 4),
                "max_height_mm": round(float(np.max(component_residual)), 4),
                "mean_height_mm": round(float(np.mean(component_residual)), 4),
                "bbox_mm": {
                    "x_min": float(lo[0]),
                    "y_min": float(lo[1]),
                    "x_max": float(hi[0]),
                    "y_max": float(hi[1]),
                },
                "bbox_normalized": {
                    "x_min": float(normalized[0]),
                    "y_min": float(normalized[1]),
                    "x_max": float(normalized[2]),
                    "y_max": float(normalized[3]),
                },
            }
        )

    regions.sort(
        key=lambda item: (item["area_mm2"], item["max_height_mm"]),
        reverse=True,
    )
    result["regions"] = regions[: max(1, int(max_regions))]
    return result


def build_protrusion_region_mask(
    pts: np.ndarray,
    detection: Dict[str, Any],
    region_index: int = 0,
) -> np.ndarray:
    """Classify rendered points belonging to one detected 3D protrusion.

    A point is highlighted only when it lies inside the connected region's
    XY extent *and* exceeds the same fitted-plane height threshold used by the
    detector.  This produces a point-level mask rather than a rectangular box.
    """
    if pts is None or getattr(pts, "ndim", 0) != 2 or pts.shape[1] < 3:
        raise ValueError("点云数据必须是包含 X、Y、Z 的二维数组")

    mask = np.zeros(len(pts), dtype=bool)
    regions = detection.get("regions") or []
    if not regions or region_index < 0 or region_index >= len(regions):
        return mask

    plane = detection.get("reference_plane") or {}
    try:
        a = float(plane["a"])
        b = float(plane["b"])
        c = float(plane["c"])
        center = float(detection.get("residual_center_mm", 0.0))
        threshold = float(detection["threshold_mm"])
        bbox = regions[region_index]["bbox_mm"]
        x_min = float(bbox["x_min"])
        x_max = float(bbox["x_max"])
        y_min = float(bbox["y_min"])
        y_max = float(bbox["y_max"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("挂渣检测结果缺少生成 3D mask 所需的数据") from exc

    xyz = np.asarray(pts[:, :3], dtype=np.float64)
    finite = np.all(np.isfinite(xyz), axis=1)
    heights = xyz[:, 2] - (a * xyz[:, 0] + b * xyz[:, 1] + c) - center
    mask = (
        finite
        & (xyz[:, 0] >= x_min)
        & (xyz[:, 0] <= x_max)
        & (xyz[:, 1] >= y_min)
        & (xyz[:, 1] <= y_max)
        & (heights >= threshold)
    )
    return mask


def detect_workpiece_image_roi(image_path: str, target_width: int = 792) -> Dict[str, Any]:
    """Locate the workpiece rectangle in the fixed inspection-camera view.

    The fixture is dark and the workpiece carries substantially more texture.
    A downscaled gradient map finds a seed on the workpiece; smoothed intensity
    projections then expand the seed to the four physical workpiece edges.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage

    source = QImage(image_path)
    if source.isNull():
        raise ValueError(f"无法读取对应的 2D 图像: {image_path}")
    original_width = source.width()
    original_height = source.height()
    scale = min(1.0, float(target_width) / max(1, original_width))
    if scale < 1.0:
        image = source.scaledToWidth(
            max(200, int(round(original_width * scale))),
            Qt.TransformationMode.SmoothTransformation,
        )
    else:
        image = source
    gray = image.convertToFormat(QImage.Format.Format_Grayscale8)
    buffer = gray.bits().asstring(gray.sizeInBytes())
    pixels = np.frombuffer(buffer, dtype=np.uint8).reshape(
        gray.height(),
        gray.bytesPerLine(),
    )[:, : gray.width()].astype(np.float64)
    height, width = pixels.shape

    gradient = np.zeros_like(pixels)
    gradient[:, 1:] += np.abs(pixels[:, 1:] - pixels[:, :-1])
    gradient[1:, :] += np.abs(pixels[1:, :] - pixels[:-1, :])
    kernel = max(15, int(round(width * 0.032)))
    integral = np.pad(gradient, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    local_texture = (
        integral[kernel:, kernel:]
        - integral[:-kernel, kernel:]
        - integral[kernel:, :-kernel]
        + integral[:-kernel, :-kernel]
    ) / float(kernel * kernel)

    x0 = int(0.25 * width)
    x1 = max(x0 + 1, int(0.60 * width) - kernel + 1)
    y0 = int(0.40 * height)
    y1 = max(y0 + 1, int(0.72 * height) - kernel + 1)
    search = local_texture[y0:y1, x0:x1]
    if search.size == 0:
        raise ValueError("2D 图像尺寸不足，无法定位工件")
    seed_y, seed_x = np.unravel_index(np.argmax(search), search.shape)
    seed_x += x0 + kernel // 2
    seed_y += y0 + kernel // 2

    def projection_bounds(
        profile: np.ndarray,
        seed: int,
        span: int,
    ) -> tuple[int, int]:
        lo = max(0, seed - span)
        hi = min(len(profile), seed + span + 1)
        values = profile[lo:hi]
        smooth_width = max(5, int(round(len(profile) * 0.009)))
        if smooth_width % 2 == 0:
            smooth_width += 1
        smooth = np.convolve(
            values,
            np.ones(smooth_width) / smooth_width,
            mode="same",
        )
        baseline = float(np.percentile(smooth, 25))
        peak = float(np.percentile(smooth, 85))
        threshold = baseline + max(2.5, 0.28 * (peak - baseline))
        mask = smooth > threshold

        # Close narrow dark gaps such as the laser-cut slit itself.
        index = 0
        max_gap = max(4, int(round(len(profile) * 0.010)))
        while index < len(mask):
            if mask[index]:
                index += 1
                continue
            gap_start = index
            while index < len(mask) and not mask[index]:
                index += 1
            if (
                gap_start > 0
                and index < len(mask)
                and index - gap_start <= max_gap
            ):
                mask[gap_start:index] = True

        runs = []
        index = 0
        while index < len(mask):
            if not mask[index]:
                index += 1
                continue
            run_start = index
            while index < len(mask) and mask[index]:
                index += 1
            runs.append((run_start + lo, index + lo))
        if not runs:
            return max(0, seed - span // 2), min(len(profile), seed + span // 2)
        containing = [run for run in runs if run[0] <= seed < run[1]]
        if containing:
            return max(containing, key=lambda run: run[1] - run[0])
        return min(runs, key=lambda run: abs((run[0] + run[1]) / 2.0 - seed))

    y_band = pixels[
        max(0, seed_y - int(0.07 * height)) :
        min(height, seed_y + int(0.07 * height) + 1)
    ]
    roi_x0, roi_x1 = projection_bounds(
        np.mean(y_band, axis=0),
        seed_x,
        int(0.18 * width),
    )
    x_band = pixels[:, roi_x0:roi_x1]
    roi_y0, roi_y1 = projection_bounds(
        np.mean(x_band, axis=1),
        seed_y,
        int(0.22 * height),
    )

    inverse_scale_x = original_width / float(width)
    inverse_scale_y = original_height / float(height)
    bbox = {
        "x_min": int(round(roi_x0 * inverse_scale_x)),
        "y_min": int(round(roi_y0 * inverse_scale_y)),
        "x_max": int(round(roi_x1 * inverse_scale_x)),
        "y_max": int(round(roi_y1 * inverse_scale_y)),
    }
    return {
        "image_width": int(original_width),
        "image_height": int(original_height),
        "workpiece_bbox_px": bbox,
        "method": "fixed-fixture-texture-projection",
    }


def map_protrusions_to_image(
    detection: Dict[str, Any],
    image_roi: Dict[str, Any],
    transform: str = "rotate_ccw",
    padding_px: int = 8,
) -> Dict[str, Any]:
    """Project normalized 3D protrusion boxes into the 2D workpiece ROI."""
    roi = image_roi["workpiece_bbox_px"]
    roi_width = max(1.0, float(roi["x_max"] - roi["x_min"]))
    roi_height = max(1.0, float(roi["y_max"] - roi["y_min"]))
    image_width = int(image_roi["image_width"])
    image_height = int(image_roi["image_height"])

    def transform_point(x: float, y: float) -> tuple[float, float]:
        if transform == "rotate_ccw":
            return 1.0 - y, x
        if transform == "rotate_cw":
            return y, 1.0 - x
        if transform == "flip_x":
            return 1.0 - x, y
        if transform == "flip_y":
            return x, 1.0 - y
        return x, y

    boxes = []
    for index, region in enumerate(detection.get("regions", []), start=1):
        box = region["bbox_normalized"]
        corners = [
            transform_point(box["x_min"], box["y_min"]),
            transform_point(box["x_min"], box["y_max"]),
            transform_point(box["x_max"], box["y_min"]),
            transform_point(box["x_max"], box["y_max"]),
        ]
        u_values = [point[0] for point in corners]
        v_values = [point[1] for point in corners]
        x_min = int(round(roi["x_min"] + min(u_values) * roi_width))
        x_max = int(round(roi["x_min"] + max(u_values) * roi_width))
        y_min = int(round(roi["y_min"] + min(v_values) * roi_height))
        y_max = int(round(roi["y_min"] + max(v_values) * roi_height))
        x_min = max(0, x_min - int(padding_px))
        y_min = max(0, y_min - int(padding_px))
        x_max = min(image_width - 1, x_max + int(padding_px))
        y_max = min(image_height - 1, y_max + int(padding_px))
        boxes.append(
            {
                "label": f"挂渣 {index}",
                "x_min": x_min,
                "y_min": y_min,
                "x_max": x_max,
                "y_max": y_max,
                "max_height_mm": region["max_height_mm"],
                "mean_height_mm": region["mean_height_mm"],
                "area_mm2": region["area_mm2"],
            }
        )
    return {
        **image_roi,
        "transform": transform,
        "threshold_mm": detection["threshold_mm"],
        "boxes": boxes,
    }

def auto_archive_local_directory(src_dir: str) -> Dict[str, Any]:
    """
    Scans a local directory for files, automatically associates them to experiment IDs
    and slot names based on filename patterns, archives them, and updates the DB.
    """
    if not src_dir or not os.path.exists(src_dir):
        return {"status": "error", "message": f"目录 '{src_dir}' 不存在"}

    # Get all active run IDs
    runs = get_all_runs()
    episode_ids = [r["episode_id"] for r in runs]
    if not episode_ids:
        return {"status": "error", "message": "数据库中尚无任何试验记录"}

    # List all files in source folder
    try:
        all_files = [f for f in os.listdir(src_dir) if os.path.isfile(os.path.join(src_dir, f))]
    except Exception as e:
        return {"status": "error", "message": f"无法读取目录内容: {e}"}

    pc_extensions = {".ply", ".pcd", ".xyz", ".pts", ".asc", ".csv"}
    img_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}

    pc_mapping = {
        "point_cloud_front": ["front", "qian", "qianqiemian", "pc_front", "pc1", "01mian", "1mian"],
        "point_cloud_back": ["back", "hou", "houqiemian", "pc_back", "pc2", "02mian", "2mian"],
        "point_cloud_left": ["left", "zuo", "zuoqiemian", "pc_left", "pc3", "03mian", "3mian"],
        "point_cloud_right": ["right", "you", "youqiemian", "pc_right", "pc4", "04mian", "4mian"],
        "point_cloud_top": ["top", "shang", "shangbiaomian", "pc_top", "pc_up", "up"],
        "point_cloud_dross": ["dross", "slag", "dizha", "guazha", "pc_dross", "pc_down", "pc5", "05mian", "5mian", "down", "xia", "bottom"]
    }
    
    img_mapping = {
        "image_front": ["front", "qian", "qianqiemian", "img_front", "img1", "01mian", "1mian"],
        "image_back": ["back", "hou", "houqiemian", "img_back", "img2", "02mian", "2mian"],
        "image_left": ["left", "zuo", "img_left", "img3", "03mian", "3mian"],
        "image_right": ["right", "you", "img_right", "img4", "04mian", "4mian"],
        "image_top": ["top", "shang", "shangbiaomian", "img_top", "img5", "up", "luminance_up", "up_luminance"],
        "image_bottom": ["bottom", "xia", "xiabiaomian", "img_bottom", "img6", "down", "luminance_down", "down_luminance"]
    }


def import_luminance_images(episode_id: str, file_paths: List[str]) -> Dict[str, Any]:
    """
    Accepts a list of selected image files (including Keyence TIF / Luminance images),
    automatically detects orientation keywords ('up'/'top'/'shang' -> image_top; 'down'/'bottom'/'xia'/'dross' -> image_bottom),
    converts TIF to PNG preview if needed, saves them to inspections directory, and updates DB.
    """
    if not episode_id:
        return {"status": "error", "message": "未指定试验 ID"}
    if not file_paths:
        return {"status": "error", "message": "未选择任何亮度图文件"}

    imported_count = 0
    assigned_slots = {}
    
    up_keywords = ["up", "top", "shang", "shangbiaomian", "05mian", "5mian", "5"]
    down_keywords = ["down", "bottom", "xia", "xiabiaomian", "dross", "slag", "dizha", "guazha", "06mian", "6mian", "6"]

    runs = get_all_runs()
    run = next((r for r in runs if r["episode_id"] == episode_id), {})

    for src_path in file_paths:
        if not src_path or not os.path.exists(src_path):
            continue
        filename = os.path.basename(src_path).lower()
        
        target_slot = None
        if any(kw in filename for kw in up_keywords):
            target_slot = "image_top"
        elif any(kw in filename for kw in down_keywords):
            target_slot = "image_bottom"
        else:
            # Fallback if no direction keyword specified in filename
            if "image_top" not in assigned_slots and not run.get("image_top"):
                target_slot = "image_top"
            elif "image_bottom" not in assigned_slots and not run.get("image_bottom"):
                target_slot = "image_bottom"
            else:
                target_slot = "image_top"
                
        rel_path = save_local_inspection_file(episode_id, target_slot, src_path)
        if rel_path:
            imported_count += 1
            assigned_slots[target_slot] = os.path.basename(rel_path)

    return {
        "status": "success",
        "imported_count": imported_count,
        "assigned_slots": assigned_slots,
        "message": f"成功选择导入 {imported_count} 个亮度图文件"
    }

    archived_count = 0
    details = {}

    def normalize(s):
        return "".join(c for c in s.lower() if c.isalnum())

    # We match files to episode IDs
    import re
    for filename in all_files:
        ext = os.path.splitext(filename)[1].lower()
        is_pc = ext in pc_extensions
        is_img = ext in img_extensions
        if not (is_pc or is_img):
            continue

        normalized_filename = normalize(filename)
        
        # 1. Try matching by block/trial number index (e.g. "01kuai" matches "SY-n001-v5-p6-f6")
        matched_id = None
        
        # Extract number from filename (e.g. "01" from "01kuai-01mian.pcd" -> 1)
        file_num = None
        m = re.search(r'(\d+)kuai', filename.lower())
        if m:
            file_num = int(m.group(1))
            
        if file_num is not None:
            # Find the episode_id that has the matching sequence number
            for eid in episode_ids:
                eid_num = None
                # Supports both the legacy SY-001 form and the new SY-n001 form.
                eid_num = extract_episode_number(eid)
                if eid_num is None:
                    # Fallback regex numeric extraction
                    num_match = re.search(r'\d+', eid)
                    if num_match:
                        eid_num = int(num_match.group())
                        
                if eid_num == file_num:
                    matched_id = eid
                    break
                    
        # 2. Fallback to normal substring matching
        if not matched_id:
            for eid in episode_ids:
                if normalize(eid) in normalized_filename:
                    matched_id = eid
                    break

        if not matched_id:
            continue

        # Check which slot it matches
        mapping = pc_mapping if is_pc else img_mapping
        matched_field = None
        
        # 1. Match by keyword list
        for field, keywords in mapping.items():
            if any(kw in normalized_filename for kw in keywords):
                matched_field = field
                break
                
        if not matched_field:
            continue

        # Execute archive copy
        src_path = os.path.join(src_dir, filename)
        rel_path = save_local_inspection_file(matched_id, matched_field, src_path)
        if rel_path:
            archived_count += 1
            if matched_id not in details:
                details[matched_id] = []
            details[matched_id].append(matched_field)

    return {
        "status": "success",
        "archived_count": archived_count,
        "details": details
    }

# Initialize DB on load
init_db()
