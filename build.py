# -*- coding: utf-8 -*-
"""
Work Tools 打包脚本
自动打包Django项目为可移植版本
"""
import os
import sys
import subprocess
from pathlib import Path


def check_python():
    """检查Python环境"""
    print("=" * 60)
    print("Work Tools Build Script")
    print("=" * 60)
    print()
    
    try:
        result = subprocess.run(
            [sys.executable, "--version"],
            capture_output=True,
            text=True
        )
        print(f"[Step 1/4] Python version: {result.stdout.strip()}")
        return True
    except Exception as e:
        print(f"[ERROR] Python not found: {e}")
        input("Press Enter to exit...")
        return False


def install_pyinstaller():
    """安装PyInstaller"""
    print("\n[Step 2/4] Installing PyInstaller...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller", "-q"],
            check=True
        )
        print("[OK] PyInstaller installed")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to install PyInstaller: {e}")
        input("Press Enter to exit...")
        return False


def generate_requirements():
    """生成requirements.txt"""
    print("\n[Step 3/4] Generating requirements.txt...")
    req_file = Path("requirements.txt")
    
    if not req_file.exists():
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "freeze"],
                capture_output=True,
                text=True,
                check=True
            )
            with open("requirements.txt", "w", encoding="utf-8") as f:
                f.write(result.stdout)
            print("[OK] Generated requirements.txt")
        except Exception as e:
            print(f"[WARNING] Failed to generate requirements.txt: {e}")
    else:
        print("[OK] requirements.txt already exists")
    
    return True


def build_project():
    """打包项目"""
    print("\n[Step 4/4] Building project...")
    print("This may take a few minutes, please wait...\n")
    
    # 清理旧的打包文件
    import shutil
    if Path("dist").exists():
        print("Cleaning old dist folder...")
        shutil.rmtree("dist")
    if Path("build").exists():
        shutil.rmtree("build")
    for spec_file in Path(".").glob("*.spec"):
        spec_file.unlink()
    
    # 构建pyinstaller命令
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        "--onedir",
        "--name", "WorkTools",
        "--add-data", f"templates{os.pathsep}templates",
        "--add-data", f"static{os.pathsep}static",
        "--add-data", f"work_tools2{os.pathsep}work_tools2",
        "--add-data", f"manage.py{os.pathsep}.",
        "--hidden-import=django",
        "--hidden-import=pypinyin",
        "--hidden-import=sqlite3",
        "--collect-all", "django",
        "--console",
        "launcher.py"
    ]
    
    print(f"Running command: {' '.join(cmd)}\n")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print("\n[OK] Build completed!")
        return True
    except Exception as e:
        print(f"\n[ERROR] Build failed: {e}")
        input("Press Enter to exit...")
        return False


def copy_files():
    """复制必要文件"""
    print("\nCopying necessary files...")
    
    dist_dir = Path("dist/WorkTools")
    
    if not dist_dir.exists():
        print(f"[ERROR] Dist directory not found: {dist_dir}")
        return False
    
    # 复制数据库
    if Path("db.sqlite3").exists():
        import shutil
        shutil.copy2("db.sqlite3", dist_dir)
        print("[OK] Database copied")
    else:
        print("[WARNING] db.sqlite3 not found, will be created on first run")
    
    # 复制使用说明
    if Path("使用说明.txt").exists():
        import shutil
        shutil.copy2("使用说明.txt", dist_dir)
        print("[OK] README copied")
    
    # 创建英文README
    readme_content = """Work Tools - Usage Instructions

How to start:
1. Double-click WorkTools.exe
2. Wait a few seconds
3. Browser will open automatically

Access URL:
http://127.0.0.1:9123

How to stop:
Close the console window

Note:
- First startup may be slow
- Make sure port 9123 is not in use
- Allow firewall access if prompted
"""
    
    with open(dist_dir / "README.txt", "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("[OK] README.txt created")
    
    # 验证必要文件
    print("\nVerifying packaged files...")
    required_dirs = [
        dist_dir / "templates",
        dist_dir / "static",
        dist_dir / "work_tools2",
    ]
    
    required_files = [
        dist_dir / "manage.py",
        dist_dir / "WorkTools.exe",
    ]
    
    all_ok = True
    for dir_path in required_dirs:
        if dir_path.exists():
            print(f"  [OK] {dir_path.name}/")
        else:
            print(f"  [MISSING] {dir_path.name}/")
            all_ok = False
    
    for file_path in required_files:
        if file_path.exists():
            print(f"  [OK] {file_path.name}")
        else:
            print(f"  [MISSING] {file_path.name}")
            all_ok = False
    
    if all_ok:
        print("\n[OK] All required files present!")
    else:
        print("\n[WARNING] Some files are missing!")
    
    return all_ok


def main():
    """主函数"""
    # 切换到项目根目录
    os.chdir(Path(__file__).parent)
    
    # 执行打包步骤
    if not check_python():
        return
    
    if not install_pyinstaller():
        return
    
    if not generate_requirements():
        return
    
    if not build_project():
        return
    
    if not copy_files():
        print("\n[WARNING] Build completed but some files are missing!")
        print("The application may not work correctly.")
    
    print("\n" + "=" * 60)
    print("Build Completed Successfully!")
    print("=" * 60)
    print(f"\nOutput folder: {Path('dist/WorkTools').absolute()}")
    print("\nHow to use:")
    print("1. Copy the entire WorkTools folder to target PC")
    print("2. Double-click WorkTools.exe")
    print("3. Browser will open at http://127.0.0.1:9123")
    print("\nNote: First startup may be slow, please be patient")
    print("=" * 60)
    
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
