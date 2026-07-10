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


def vacuum_database():
    """对 db.sqlite3 执行 VACUUM 压缩，减小打包体积"""
    db_path = Path("db.sqlite3")
    if not db_path.exists():
        print("[INFO] db.sqlite3 not found, skipping vacuum")
        return True
    
    print("\n[Vacuum] Compressing database...")
    try:
        import sqlite3
        size_before = db_path.stat().st_size
        conn = sqlite3.connect(str(db_path))
        conn.execute("VACUUM")
        conn.close()
        size_after = db_path.stat().st_size
        saved_mb = (size_before - size_after) / (1024 * 1024)
        print(f"[OK] Database compressed: {size_before / (1024 * 1024):.1f} MB -> {size_after / (1024 * 1024):.1f} MB (saved {saved_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"[WARNING] Failed to vacuum database: {e}")
        return True  # 不影响后续打包


def build_project():
    """打包项目"""
    print("\n[Step 4/4] Building project...")
    print("This may take a few minutes, please wait...\n")

    # 清理旧的打包文件
    import shutil
    import time

    if Path("dist").exists():
        print("Cleaning old dist folder...")
        try:
            shutil.rmtree("dist")
        except PermissionError as e:
            print(f"[WARNING] Cannot delete dist folder: {e}")
            print("[INFO] Trying alternative method...")

            # 尝试重命名后再删除
            retry_count = 0
            max_retries = 3

            while retry_count < max_retries:
                try:
                    # 重命名为临时名称
                    temp_name = f"dist_old_{int(time.time())}"
                    os.rename("dist", temp_name)

                    # 异步删除旧文件夹
                    import threading
                    def delete_later(folder_name):
                        time.sleep(2)  # 等待2秒
                        try:
                            shutil.rmtree(folder_name, ignore_errors=True)
                        except:
                            pass

                    thread = threading.Thread(target=delete_later, args=(temp_name,))
                    thread.daemon = True
                    thread.start()

                    print(f"[OK] Renamed old dist to {temp_name} (will be deleted automatically)")
                    break
                except Exception as rename_error:
                    retry_count += 1
                    if retry_count < max_retries:
                        print(f"[RETRY {retry_count}/{max_retries}] Waiting 1 second...")
                        time.sleep(1)
                    else:
                        print(f"[ERROR] Failed to clean dist folder after {max_retries} retries")
                        print(f"[ERROR] Please manually delete the 'dist' folder and try again")
                        input("Press Enter to exit...")
                        return False

    if Path("build").exists():
        try:
            shutil.rmtree("build")
        except:
            print("[WARNING] Cannot delete build folder, skipping...")

    for spec_file in Path(".").glob("*.spec"):
        try:
            spec_file.unlink()
        except:
            pass

    # 压缩数据库以减小打包体积
    vacuum_database()

    # 检测 UPX
    upx_dir = None
    try:
        upx_result = subprocess.run(["upx", "--version"], capture_output=True, text=True)
        if upx_result.returncode == 0:
            upx_dir = "."
            print("[OK] UPX detected, will be used for compression")
    except Exception:
        print("[INFO] UPX not found, skipping UPX compression")

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
        # 核心依赖隐式导入
        "--hidden-import=django",
        "--hidden-import=django.contrib.admin",
        "--hidden-import=django.contrib.auth",
        "--hidden-import=django.contrib.contenttypes",
        "--hidden-import=django.contrib.sessions",
        "--hidden-import=django.contrib.messages",
        "--hidden-import=django.contrib.staticfiles",
        "--hidden-import=pypinyin",
        "--hidden-import=pypinyin.pinyin_dict",
        "--hidden-import=pypinyin.style",
        "--hidden-import=sqlite3",
        "--hidden-import=xlrd",
        "--hidden-import=sqlparse",
        "--hidden-import=et_xmlfile",
        # 数据文件收集（比 --collect-all 更精简）
        "--collect-data", "pypinyin",
        "--collect-data", "django",
        "--collect-data", "openpyxl",
        "--collect-data", "tkinter",
        # tkinter 运行时依赖
        "--hidden-import=tkinter",
        "--hidden-import=tkinter.filedialog",
        # 排除常见但未使用的重型包（若环境中有安装）
        "--exclude-module", "matplotlib",
        "--exclude-module", "numpy",
        "--exclude-module", "pandas",
        "--exclude-module", "PyQt5",
        "--exclude-module", "PyQt6",
        "--exclude-module", "PySide2",
        "--exclude-module", "PySide6",
        "--exclude-module", "scipy",
        "--exclude-module", "sklearn",
        "--exclude-module", "tensorflow",
        "--exclude-module", "torch",
        "--console",
        "launcher.py"
    ]

    if upx_dir:
        cmd.insert(5, "--upx-dir")
        cmd.insert(6, upx_dir)

    print(f"Running command: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print("\n[OK] PyInstaller build completed!")
        return True
    except Exception as e:
        print(f"\n[ERROR] Build failed: {e}")
        input("Press Enter to exit...")
        return False


def cleanup_package(internal_dir):
    """清理打包后不需要的文件，减小体积"""
    print("\nCleaning up unnecessary files...")
    import shutil
    
    removed_count = 0
    removed_size = 0
    
    # 删除测试、文档、缓存目录
    patterns_to_remove = [
        "**/tests",
        "**/test",
        "**/docs",
        "**/doc",
        "**/__pycache__",
        "**/*.pyc",
        "**/*.pyo",
        "**/*.dist-info/REQUESTED",
        "**/django/contrib/gis",
        "**/django/contrib/redirects",
        "**/django/contrib/sitemaps",
        "**/django/contrib/syndication",
        "**/django/contrib/humanize",
        "**/django/contrib/postgres",
        "**/openpyxl/charts",
        "**/openpyxl/drawing",
        "**/openpyxl/chartsheet",
        "**/openpyxl/pivot",
        "**/openpyxl/workbook/external_link",
    ]
    
    for pattern in patterns_to_remove:
        for path in internal_dir.glob(pattern):
            try:
                if path.is_dir():
                    removed_size += sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    removed_size += path.stat().st_size
                    path.unlink(missing_ok=True)
                removed_count += 1
            except Exception:
                pass
    
    print(f"[OK] Removed {removed_count} items, freed {removed_size / (1024 * 1024):.1f} MB")


def copy_files():
    """复制必要文件"""
    print("\nCopying necessary files...")
    
    dist_dir = Path("dist/WorkTools")
    internal_dir = dist_dir / "_internal"
    
    if not dist_dir.exists():
        print(f"[ERROR] Dist directory not found: {dist_dir}")
        return False
    
    # 注意：db.sqlite3 由 PyInstaller 自动打包到 _internal 目录，
    # 不再额外复制一份到根目录，避免重复并减小体积。
    
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
1. Recommended: Press Ctrl+C in the console window and wait for the exit message before closing.
2. Or close the console window directly.

If you cannot delete/replace the WorkTools folder after closing (folder in use):
The WorkTools.exe process may still be running in the background. Please end it first:
1. Open Task Manager (Ctrl+Shift+Esc).
2. Find WorkTools.exe in Processes/Details.
3. Click "End task".
4. Try deleting/replacing the folder again.

Or run this command:
taskkill /f /im WorkTools.exe

Note:
- First startup may be slow
- Make sure port 9123 is not in use
- Allow firewall access if prompted
- Closing the console window directly may leave the process running for a while and lock the folder
"""
    
    with open(dist_dir / "README.txt", "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("[OK] README.txt created")
    
    # 清理不必要的文件以减小体积
    if internal_dir.exists():
        cleanup_package(internal_dir)
    
    # 验证必要文件
    print("\nVerifying packaged files...")
    required_dirs = [
        dist_dir / "templates",
        dist_dir / "static",
        dist_dir / "work_tools2",
        internal_dir,
    ]
    
    required_files = [
        dist_dir / "manage.py",
        dist_dir / "WorkTools.exe",
        internal_dir / "db.sqlite3",
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
