import os
import sys
import sqlite3
import numpy as np

# Adjust python path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import gui_db

def generate_demo():
    print("[*] Generating demo files...")
    
    # 1. Create a dummy run in SQLite
    episode_id = "Demo-Run"
    conn = sqlite3.connect(gui_db.DB_FILE)
    cursor = conn.cursor()
    
    # Check if exists, delete first to refresh
    cursor.execute("DELETE FROM experiment_runs WHERE episode_id = ?;", (episode_id,))
    
    # Insert new run
    cursor.execute("""
        INSERT INTO experiment_runs (
            episode_id, stage, material, thickness_mm, gas, power_kw, speed_m_min,
            air_pressure_mpa, focus_mm, energy_index, cut_through, failure_case, quality_score, manual_comment
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        episode_id, "manual_run", "carbon_steel", 30.0, "air", 49.8, 0.8,
        1.5, -9.0, 62.25, 1, "normal", 85.0, "三维点云与图像预览测试数据"
    ))
    conn.commit()
    conn.close()
    
    # Create inspections folder
    dest_dir = os.path.join(gui_db.INSPECTION_DIR, episode_id)
    os.makedirs(dest_dir, exist_ok=True)
    
    # Generate points (a neat 3D sphere)
    num_points = 2000
    phi = np.random.uniform(0, 2 * np.pi, num_points)
    costheta = np.random.uniform(-1, 1, num_points)
    theta = np.arccos(costheta)
    r = np.random.uniform(0, 5.0, num_points) # radius up to 5mm
    
    x = r * np.sin(theta) * np.cos(phi)
    y = r * np.sin(theta) * np.sin(phi)
    z = r * np.cos(theta)
    
    # Write PCD (ASCII)
    pcd_path = os.path.join(dest_dir, f"{episode_id}_point_cloud_front.pcd")
    with open(pcd_path, "w", encoding="utf-8") as f:
        f.write("# .PCD v0.7 - Point Cloud Data\n")
        f.write("VERSION 0.7\n")
        f.write("FIELDS x y z\n")
        f.write("SIZE 4 4 4\n")
        f.write("TYPE F F F\n")
        f.write("COUNT 1 1 1\n")
        f.write("WIDTH {}\n".format(num_points))
        f.write("HEIGHT 1\n")
        f.write("VIEWPOINT 0 0 0 1 0 0 0\n")
        f.write("POINTS {}\n".format(num_points))
        f.write("DATA ascii\n")
        for i in range(num_points):
            f.write(f"{x[i]:.4f} {y[i]:.4f} {z[i]:.4f}\n")
    print(f"[OK] Created PCD: {pcd_path}")
    
    # Write ASC
    asc_path = os.path.join(dest_dir, f"{episode_id}_point_cloud_back.asc")
    with open(asc_path, "w", encoding="utf-8") as f:
        for i in range(num_points):
            f.write(f"{x[i]:.4f} {y[i]:.4f} {z[i]:.4f}\n")
    print(f"[OK] Created ASC: {asc_path}")
    
    # Write CSV
    csv_path = os.path.join(dest_dir, f"{episode_id}_point_cloud_left.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("X,Y,Z\n") # Add header
        for i in range(num_points):
            f.write(f"{x[i]:.4f},{y[i]:.4f},{z[i]:.4f}\n")
    print(f"[OK] Created CSV: {csv_path}")
    
    # Generate TIF image using PyQt6 QImage
    tif_path = os.path.join(dest_dir, f"{episode_id}_image_top.tif")
    
    from PyQt6.QtGui import QGuiApplication, QImage, QColor, QPainter
    qt_app = QGuiApplication([])
    img = QImage(400, 400, QImage.Format.Format_RGB32)
    img.fill(QColor(15, 23, 42)) # Slate 900 background
    
    p = QPainter(img)
    p.setPen(QColor(56, 189, 248)) # Cyan line
    p.drawRect(50, 50, 300, 300)
    p.setBrush(QColor(239, 68, 68)) # Red circle
    p.drawEllipse(150, 150, 100, 100)
    p.setPen(QColor(255, 255, 255))
    p.drawText(80, 80, "Laser Cutting Specimen")
    p.drawText(80, 100, "Demo TIFF Image")
    p.end()
    
    img.save(tif_path, "TIFF")
    print(f"[OK] Created TIFF: {tif_path}")
    
    # Auto convert TIFF to PNG so the Web UI has the png copy immediately
    png_path = os.path.join(dest_dir, f"{episode_id}_image_top.png")
    gui_db.convert_tif_to_png(tif_path, png_path)
    
    # Update SQLite records with relative paths
    conn = sqlite3.connect(gui_db.DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE experiment_runs SET
            point_cloud_front = ?,
            point_cloud_back = ?,
            point_cloud_left = ?,
            image_top = ?
        WHERE episode_id = ?;
    """, (
        f"data/inspections/{episode_id}/{episode_id}_point_cloud_front.pcd",
        f"data/inspections/{episode_id}/{episode_id}_point_cloud_back.asc",
        f"data/inspections/{episode_id}/{episode_id}_point_cloud_left.csv",
        f"data/inspections/{episode_id}/{episode_id}_image_top.tif",
        episode_id
    ))
    conn.commit()
    conn.close()
    
    # Sync SQLite to CSV and JSON logs
    gui_db.sync_data_to_files()
    print("[*] Done! Demo registered and logs synced successfully.")

if __name__ == "__main__":
    generate_demo()
