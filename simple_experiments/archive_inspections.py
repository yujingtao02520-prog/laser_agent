import os
import sys
import shutil
import argparse

# Add src folder to Python path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import gui_db

def match_and_archive(episode_id: str, src_dir: str):
    if not os.path.exists(src_dir):
        print(f"[错误] 源文件目录 '{src_dir}' 不存在！")
        return False
        
    print(f"[*] 开始为试验 ID [{episode_id}] 自动归档检测文件...")
    print(f"[*] 扫描目录: {os.path.abspath(src_dir)}")
    
    # Get all files in source directory
    all_files = [f for f in os.listdir(src_dir) if os.path.isfile(os.path.join(src_dir, f))]
    
    pc_extensions = {".ply", ".pcd", ".xyz", ".pts"}
    img_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}
    
    pc_files = [f for f in all_files if os.path.splitext(f)[1].lower() in pc_extensions]
    img_files = [f for f in all_files if os.path.splitext(f)[1].lower() in img_extensions]
    
    # Keywords matching maps
    pc_mapping = {
        "point_cloud_front": ["front", "qian", "qianqiemian", "1"],
        "point_cloud_back": ["back", "hou", "houqiemian", "2"],
        "point_cloud_left": ["left", "zuo", "zuoqiemian", "3"],
        "point_cloud_right": ["right", "you", "youqiemian", "4"],
        "point_cloud_dross": ["dross", "slag", "dizha", "zha", "guazha", "5"]
    }
    
    img_mapping = {
        "image_front": ["front", "qian", "qianqiemian", "1"],
        "image_back": ["back", "hou", "houqiemian", "2"],
        "image_left": ["left", "zuo", "zuoqiemian", "3"],
        "image_right": ["right", "you", "youqiemian", "4"],
        "image_top": ["top", "shang", "shangbiaomian", "5"],
        "image_bottom": ["bottom", "xia", "xiabiaomian", "6"]
    }
    
    pc_results = {}
    img_results = {}
    
    # Helper to find file by keywords
    def find_file_by_keywords(files_list, keywords):
        for f in files_list:
            name_lower = f.lower()
            if any(kw in name_lower for kw in keywords):
                return f
        return None

    # 1. Match Point Clouds by keywords
    for field, keywords in pc_mapping.items():
        matched = find_file_by_keywords(pc_files, keywords)
        if matched:
            pc_results[field] = matched
            pc_files.remove(matched)
            
    # 2. Match Images by keywords
    for field, keywords in img_mapping.items():
        matched = find_file_by_keywords(img_files, keywords)
        if matched:
            img_results[field] = matched
            img_files.remove(matched)

    # 3. Fallback to index-based matching for remaining empty slots
    pc_files.sort()
    img_files.sort()
    
    remaining_pc_slots = [s for s in pc_mapping.keys() if s not in pc_results]
    for slot in remaining_pc_slots:
        if pc_files:
            matched_file = pc_files.pop(0)
            pc_results[slot] = matched_file
            print(f"[提示] 未能用关键字匹配到 {slot}，使用剩余点云文件排序兜底: '{matched_file}'")
            
    remaining_img_slots = [s for s in img_mapping.keys() if s not in img_results]
    for slot in remaining_img_slots:
        if img_files:
            matched_file = img_files.pop(0)
            img_results[slot] = matched_file
            print(f"[提示] 未能用关键字匹配到 {slot}，使用剩余图像文件排序兜底: '{matched_file}'")
            
    # Execute archiving via DB utility
    archived_count = 0
    all_results = {**pc_results, **img_results}
    
    for field_name, filename in all_results.items():
        src_path = os.path.join(src_dir, filename)
        rel_path = gui_db.save_local_inspection_file(episode_id, field_name, src_path)
        if rel_path:
            print(f"[✓] 成功归档: '{filename}' -> '{rel_path}'")
            archived_count += 1
            
    print(f"[*] 归档结束！共为试验 [{episode_id}] 整理归档了 {archived_count} 个检测文件。")
    return archived_count > 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="自动扫描、命名、整理归档试验的图片与点云文件")
    parser.add_argument("--id", type=str, help="试验 ID (如 SY-5-6-6-001)，如果不指定，默认使用最后一次试验记录")
    parser.add_argument("--dir", type=str, default=".", help="临时照片和点云的文件夹路径 (默认是当前文件夹)")
    args = parser.parse_args()
    
    # If ID not specified, query last run from DB
    episode_id = args.id
    if not episode_id:
        last_params = gui_db.get_last_run_parameters()
        if last_params:
            episode_id = last_params.get("episode_id")
            print(f"[ℹ] 未指定试验 ID，默认选择最近一次试验记录: [{episode_id}]")
        else:
            print("[错误] 数据库中没有任何试验记录，请使用 --id 指定试验名称！")
            sys.exit(1)
            
    match_and_archive(episode_id, args.dir)
