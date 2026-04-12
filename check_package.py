# -*- coding: utf-8 -*-
"""
测试打包结果
检查所有必要文件是否存在
"""
import sys
from pathlib import Path


def check_packaged_app():
    """检查打包后的应用"""
    print("=" * 60)
    print("Checking Packaged Application")
    print("=" * 60)
    print()
    
    # 查找dist/WorkTools目录
    dist_dir = Path("dist/WorkTools")
    
    if not dist_dir.exists():
        print("[ERROR] dist/WorkTools directory not found!")
        print("Please run build.py first to package the application.")
        return False
    
    print(f"Found dist directory: {dist_dir.absolute()}")
    print()
    
    # 检查必要目录
    required_dirs = {
        "templates": "HTML templates",
        "static": "Static files (CSS, JS, images)",
        "work_tools2": "Django application code",
    }
    
    # 检查必要文件
    required_files = {
        "WorkTools.exe": "Main executable",
        "manage.py": "Django management script",
        "python3*.dll": "Python runtime DLL",
    }
    
    all_ok = True
    
    print("Checking directories:")
    for dir_name, description in required_dirs.items():
        dir_path = dist_dir / dir_name
        if dir_path.exists() and dir_path.is_dir():
            # 统计文件数量
            file_count = len(list(dir_path.rglob("*")))
            print(f"  [OK] {dir_name}/ - {description} ({file_count} files)")
        else:
            print(f"  [MISSING] {dir_name}/ - {description}")
            all_ok = False
    
    print("\nChecking files:")
    for file_pattern, description in required_files.items():
        if "*" in file_pattern:
            # 处理通配符
            matches = list(dist_dir.glob(file_pattern))
            if matches:
                print(f"  [OK] {matches[0].name} - {description}")
            else:
                print(f"  [MISSING] {file_pattern} - {description}")
                all_ok = False
        else:
            file_path = dist_dir / file_pattern
            if file_path.exists():
                size_mb = file_path.stat().st_size / (1024 * 1024)
                print(f"  [OK] {file_pattern} - {description} ({size_mb:.1f} MB)")
            else:
                print(f"  [MISSING] {file_pattern} - {description}")
                all_ok = False
    
    # 检查数据库（可选）
    db_file = dist_dir / "db.sqlite3"
    if db_file.exists():
        size_mb = db_file.stat().st_size / (1024 * 1024)
        print(f"\n  [OK] db.sqlite3 - Database file ({size_mb:.1f} MB)")
    else:
        print(f"\n  [INFO] db.sqlite3 - Will be created on first run")
    
    # 检查README
    readme_files = ["README.txt", "使用说明.txt"]
    readme_found = False
    for readme in readme_files:
        if (dist_dir / readme).exists():
            print(f"  [OK] {readme} - Documentation")
            readme_found = True
            break
    
    if not readme_found:
        print(f"  [WARNING] No README file found")
    
    print()
    print("=" * 60)
    if all_ok:
        print("[SUCCESS] All required files are present!")
        print("\nThe application is ready to use.")
        print(f"Location: {dist_dir.absolute()}")
        print("\nTo test:")
        print(f"  cd {dist_dir}")
        print("  WorkTools.exe")
    else:
        print("[FAILED] Some required files are missing!")
        print("\nThe application may not work correctly.")
        print("Please rebuild using: python build.py")
    print("=" * 60)
    
    return all_ok


if __name__ == "__main__":
    success = check_packaged_app()
    input("\nPress Enter to exit...")
    sys.exit(0 if success else 1)
