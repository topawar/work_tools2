"""
Django项目启动器
用于在没有Python环境的PC上运行Django项目
"""
import os
import sys
import subprocess
import webbrowser
import threading
import time
from pathlib import Path


def get_base_dir():
    """获取程序运行的基础目录"""
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe
        return Path(sys.executable).parent
    else:
        # 如果是直接运行python脚本
        return Path(__file__).parent.absolute()


def check_python_environment():
    """检查Python环境"""
    base_dir = get_base_dir()
    
    if getattr(sys, 'frozen', False):
        # 打包后的exe，直接使用当前解释器
        python_exe = sys.executable
        print(f"[OK] Using bundled Python: {python_exe}")
    else:
        # 开发环境，查找Python
        python_exe = base_dir / "python" / "python.exe"
        
        if not python_exe.exists():
            # 尝试使用当前系统的Python
            python_exe = Path(sys.executable)
            print(f"[INFO] Using system Python: {python_exe}")
        else:
            print(f"[OK] Found portable Python: {python_exe}")
    
    if not Path(python_exe).exists():
        print("错误: 找不到Python运行环境")
        print(f"期望路径: {python_exe}")
        input("按回车键退出...")
        sys.exit(1)
    
    return str(python_exe)


def setup_environment(base_dir):
    """设置环境变量"""
    # 设置Django配置
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "work_tools2.settings")
    
    # 添加项目根目录到Python路径
    project_root = str(base_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


def run_django_server(python_exe, base_dir):
    """运行Django开发服务器"""
    
    print("=" * 60)
    print("Work Tools 管理系统")
    print("=" * 60)
    print(f"Base directory: {base_dir}")
    print(f"正在启动服务器...")
    print(f"访问地址: http://127.0.0.1:9123")
    print("=" * 60)
    print()
    
    try:
        if getattr(sys, 'frozen', False):
            # 打包后的exe，直接导入Django运行
            print("[INFO] Running in packaged mode...")
            
            # 设置Django环境
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "work_tools2.settings")
            
            # 添加当前目录到Python路径
            base_dir_str = str(base_dir)
            if base_dir_str not in sys.path:
                sys.path.insert(0, base_dir_str)
            
            print(f"[INFO] Python path: {sys.path[:3]}")
            print(f"[INFO] Current dir: {os.getcwd()}")
            
            # 先打开浏览器（在启动服务器之前）
            def open_browser_later():
                time.sleep(3)
                webbrowser.open("http://127.0.0.1:9123")
                print("\n浏览器已自动打开")
            
            browser_thread = threading.Thread(target=open_browser_later, daemon=True)
            browser_thread.start()
            
            # 在主线程中直接运行Django服务器（禁用自动重载）
            from django.core.management import execute_from_command_line
            execute_from_command_line([
                'manage.py', 
                'runserver', 
                '127.0.0.1:9123',
                '--noreload'  # 禁用自动重载，打包环境下不需要
            ])
            
        else:
            # 开发环境，使用subprocess运行
            manage_py = base_dir / "manage.py"
            
            if not manage_py.exists():
                print(f"错误: 找不到manage.py文件")
                print(f"期望路径: {manage_py}")
                input("按回车键退出...")
                sys.exit(1)
            
            process = subprocess.Popen(
                [python_exe, str(manage_py), "runserver", "127.0.0.1:9123"],
                cwd=str(base_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # 等待服务器启动
            time.sleep(3)
            
            # 自动打开浏览器
            webbrowser.open("http://127.0.0.1:9123")
            
            print("\n服务器已启动，浏览器已自动打开")
            print("关闭窗口即可停止服务器\n")
            
            # 等待进程结束
            process.wait()
        
    except KeyboardInterrupt:
        print("\n正在关闭服务器...")
        if not getattr(sys, 'frozen', False):
            process.terminate()
    except SystemExit:
        # Django服务器正常退出
        pass
    except Exception as e:
        print(f"\n错误: {str(e)}")
        import traceback
        traceback.print_exc()
        input("按回车键退出...")


def main():
    """主函数"""
    base_dir = get_base_dir()
    
    print("正在初始化环境...")
    
    # 检查并获取Python解释器
    python_exe = check_python_environment()
    
    # 设置环境
    setup_environment(base_dir)
    
    # 运行Django服务器
    run_django_server(python_exe, base_dir)


if __name__ == "__main__":
    main()
