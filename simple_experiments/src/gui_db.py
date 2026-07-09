import os
import sqlite3
import pandas as pd
from typing import List, Dict, Any, Optional

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_FILE = os.path.join(DB_DIR, "orthogonal_experiments.db")
CSV_FILE = os.path.join(DB_DIR, "experiment_log.csv")
JSON_FILE = os.path.join(DB_DIR, "experiment_log.json")
SOURCE_CSV_FILE = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "正交实验demo", "data", "metadata", "experiment_log.csv"))

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
        "point_cloud_front", "point_cloud_back", "point_cloud_left", "point_cloud_right", "point_cloud_dross",
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
    
    # Auto generate episode_id if not present
    episode_id = params.get('episode_id')
    if not episode_id:
        cursor.execute("SELECT episode_id FROM experiment_runs WHERE episode_id LIKE 'LC_CS30_AIR_L9_%' ORDER BY episode_id DESC LIMIT 1;")
        last_row = cursor.fetchone()
        if last_row:
            last_id = last_row[0]
            try:
                num = int(last_id.split('_')[-1])
                new_num = num + 1
            except Exception:
                new_num = 10
            episode_id = f"LC_CS30_AIR_L9_{new_num:04d}"
        else:
            episode_id = "LC_CS30_AIR_L9_0010"
            
    # Calculate energy index: Power / Speed (kW / m/min)
    power = float(params.get('power_kw', 54))
    speed = float(params.get('speed_m_min', 0.8))
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
        float(params.get('air_pressure_mpa', 1.5)),
        float(params.get('focus_mm', -9)),
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
        if ext == ".pcd":
            # 1. Determine header size of PCD
            header_lines = 0
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    header_lines += 1
                    if line.strip().startswith("DATA ascii"):
                        break
            
            # 2. Load data section using pandas read_csv (extremely fast)
            df = pd.read_csv(file_path, skiprows=header_lines, sep=r"\s+", header=None, usecols=[0, 1, 2], dtype=np.float32)
            points = df.to_numpy()
            
        elif ext == ".ply":
            # 1. Determine header size of PLY
            header_lines = 0
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    header_lines += 1
                    if line.strip() == "end_header":
                        break
            
            df = pd.read_csv(file_path, skiprows=header_lines, sep=r"\s+", header=None, usecols=[0, 1, 2], dtype=np.float32)
            points = df.to_numpy()
            
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
        "point_cloud_dross": ["dross", "slag", "dizha", "guazha", "pc_dross", "pc5", "up", "shang"]
    }
    
    img_mapping = {
        "image_front": ["front", "qian", "qianqiemian", "img_front", "img1", "01mian", "1mian"],
        "image_back": ["back", "hou", "houqiemian", "img_back", "img2", "02mian", "2mian"],
        "image_left": ["left", "zuo", "img_left", "img3", "03mian", "3mian"],
        "image_right": ["right", "you", "img_right", "img4", "04mian", "4mian"],
        "image_top": ["top", "shang", "img_top", "img5", "up"],
        "image_bottom": ["bottom", "xia", "img_bottom", "img6"]
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
        
        # 1. Try matching by block/trial number index (e.g. "01kuai" matches "SY-001-5-6-6")
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
                # Extract number from episode_id parts separated by hyphens (e.g. "001" from "SY-001-5-6-6" -> 1)
                parts = eid.split("-")
                if len(parts) >= 2 and parts[0].upper() == "SY":
                    try:
                        eid_num = int(parts[1])
                    except ValueError:
                        pass
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
