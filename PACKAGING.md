# Work Tools 打包说明

## 📦 打包方法

### 方法一：简化打包（推荐）

直接运行 `build_simple.bat`，会自动完成所有打包步骤。

```batch
build_simple.bat
```

**优点：**
- 一键打包，简单易用
- 自动处理所有依赖
- 生成的文件夹结构清晰

**输出位置：** `dist\WorkTools\`

---

### 方法二：完整打包

如果需要更精细的控制，可以运行 `build_package.bat`。

```batch
build_package.bat
```

**特点：**
- 创建独立的Python环境
- 更小的体积
- 更适合分发

**输出位置：** `dist_portable\`

---

## 🚀 使用方法

### 在目标电脑上运行

1. **复制文件夹**
   - 将整个 `WorkTools` 文件夹复制到目标电脑任意位置

2. **运行程序**
   - 双击 `WorkTools.exe`
   - 命令行窗口会显示启动信息
   - 浏览器会自动打开 http://127.0.0.1:9123

3. **停止服务**
   - 关闭命令行窗口即可停止服务

---

## 📋 系统要求

### 开发电脑（用于打包）
- Windows 10/11
- Python 3.8 或更高版本
- pip 包管理器

### 目标电脑（运行打包后的程序）
- Windows 10/11
- **无需安装Python**
- **无需安装任何依赖**
- 建议至少 500MB 可用磁盘空间

---

## ⚙️ 配置说明

### 修改端口号

如果需要修改默认端口（9123），编辑 `manage.py` 文件：

```python
if __name__ == "__main__":
    Runserver.default_port = "9123"  # 修改这里的端口号
    main()
```

然后重新打包。

### 修改启动器

如果需要自定义启动行为，编辑 `launcher.py` 文件。

---

## 🔧 常见问题

### Q1: 打包失败怎么办？

**A:** 检查以下几点：
1. 确保已安装 Python 3.8+
2. 确保 pip 正常工作
3. 以管理员身份运行打包脚本
4. 查看错误信息，安装缺失的依赖

### Q2: 打包后的文件太大？

**A:** 这是正常的，因为包含了完整的Python环境和所有依赖。
- Django框架本身较大
- 包含SQLite数据库
- 包含所有静态文件

### Q3: 可以在Linux/Mac上运行吗？

**A:** 当前打包脚本仅支持Windows。
如需跨平台，需要：
1. 在对应平台上重新打包
2. 修改 `launcher.py` 中的路径分隔符
3. 使用对应平台的打包工具

### Q4: 数据库文件会被打包吗？

**A:** 是的，`db.sqlite3` 会被复制到输出文件夹。
如果不想包含数据，可以在打包前删除或清空数据库。

### Q5: 如何更新已部署的程序？

**A:** 
1. 在开发电脑上修改代码
2. 重新运行打包脚本
3. 将新的 `WorkTools` 文件夹复制到目标电脑
4. 如果需要保留数据，只替换程序文件，保留 `db.sqlite3`

---

## 📁 打包后的文件结构

```
WorkTools/
├── WorkTools.exe          # 主程序入口
├── manage.py              # Django管理脚本
├── db.sqlite3             # SQLite数据库
├── templates/             # HTML模板
│   ├── home.html
│   ├── base.html
│   └── ...
├── static/                # 静态文件
│   ├── css/
│   ├── js/
│   └── ...
├── work_tools2/           # Django应用
│   ├── views/
│   ├── models.py
│   ├── urls.py
│   └── ...
├── python39.dll           # Python运行时
├── _internal/             # PyInstaller内部文件
│   └── ...
└── 使用说明.txt           # 使用说明
```

---

## 💡 优化建议

### 减小打包体积

1. **清理不必要的文件**
   ```batch
   # 打包前删除
   - __pycache__/
   - *.pyc
   - .idea/
   - 临时文件
   ```

2. **排除不需要的模块**
   在 `build_simple.bat` 中添加：
   ```batch
   --exclude-module=matplotlib ^
   --exclude-module=numpy ^
   ```

3. **使用UPX压缩**
   ```batch
   pip install upx
   pyinstaller --upx-dir=<upx路径> ...
   ```

### 提升启动速度

1. **使用 --onefile 模式**（单文件exe）
   - 优点：只有一个exe文件
   - 缺点：每次启动需要解压，较慢

2. **保持 --onedir 模式**（当前默认）
   - 优点：启动快
   - 缺点：文件较多

---

## 📞 技术支持

如遇到问题，请检查：
1. Python版本是否正确
2. 所有依赖是否已安装
3. 防火墙是否阻止了端口访问
4. 是否有足够的磁盘空间

---

## 📝 更新日志

### v1.0 (2026-04-12)
- ✅ 初始版本
- ✅ 支持Windows平台
- ✅ 自动打开浏览器
- ✅ 包含完整的Python环境
- ✅ 一键打包脚本
