# ComfyUI 工作流提取器 · ComfyUI Workflow Extractor

**v1.1** · 从 ComfyUI 生成的 PNG 中还原完整工作流，并支持分区复制提示词 / 参数 / 节点 / 连接。

一款本地运行的桌面工具（macOS / Windows），也可作为纯前端页面在浏览器中使用。所有解析均在本机完成，不联网、不上传任何图片或数据。

---

## 功能特性

- **一键提取**：选择 ComfyUI 输出的 PNG，自动读取内嵌的 `workflow`（编辑器格式）与 `prompt`（API 格式）元数据。
- **四分区结构化展示**：提示词、参数、节点、连接关系分开展示，另附完整原始 JSON。
- **分区复制**：每个分区右上角有「复制全部」按钮，一键把该区内容写入系统剪贴板；每条提示词还支持单独复制。
- **完整工作流**：可一键复制 / 下载 / 直接写回图片原目录（生成同名 `.json`；双格式时额外生成 `.api.json`）。
- **跨平台剪贴板**：三级回退策略，macOS 与 Windows 均可正常复制。

---

## v1.1 更新内容

| 项目 | 说明 |
| --- | --- |
| 新增「参数」分区 | 展示 `seed` / `steps` / `cfg` / `sampler_name` / `denoise` / 模型名等标量配置 |
| 四区复制按钮 | 提示词、参数、节点、连接关系各带「复制全部」；提示词另带单条复制 |
| 修复提示词识别 | 兼容 `CLIPTextEncode` 的 `text` 输入键（旧版仅匹配 `prompt`，导致提示词区常为空） |
| 修复连接解析 | 兼容 API 格式中字符串型节点 ID（如 `["4", 0]`），旧版仅认数字导致连接数为 0 |
| 剪贴板三级回退 | `navigator.clipboard` → Python 桥接（macOS `pbcopy` / Windows `ctypes` 剪贴板）→ `execCommand` |
| 版本号统一 | 应用标题、页面标题、Bundle 版本、安装包文件名统一为 1.1 |

---

## 安装

预编译包也可从本仓库直接下载：<https://github.com/sailor0990/comfyui-workflow-extractor/tree/main/packages>。
CI 每次推送会自动构建 macOS 与 Windows 包，可在 [Actions](https://github.com/sailor0990/comfyui-workflow-extractor/actions) 页面下载 Artifacts。

### macOS

- `packages/macos/ComfyUI-Workflow-Extractor-v1.1-macOS.dmg` — 双击挂载，把 App 拖入「应用程序」。
- `packages/macos/ComfyUI-Workflow-Extractor-v1.1-macOS.pkg` — 双击走标准安装向导，安装到 `/Applications`。

> App 未做代码签名。首次打开若被拦截：右键 → 打开；或执行
> `sudo xattr -dr com.apple.quarantine "/Applications/ComfyUI Workflow Extractor.app"`

### Windows

- `packages/windows/ComfyUI-Workflow-Extractor-v1.1-Windows.zip` — 解压后双击 `ComfyUI-Workflow-Extractor.exe`。

> 依赖系统自带的 **WebView2 Runtime**（Windows 10/11 默认内置）。较旧的 LTSC 版本请从
> <https://developer.microsoft.com/microsoft-edge/webview2/> 安装。

---

## 使用

1. 打开应用 → 点击「选择图片」，或把 PNG 拖入窗口。
2. 页面按分区展示：**提示词**、**参数**、**节点**、**连接关系**、**原始 JSON**。
3. 需要哪部分就点该区右上角的「复制全部」；提示词还可单条复制。
4. 点「保存到原目录」即在 PNG 同目录生成同名 `.json`（双格式时另生成 `.api.json`）。

---

## 提取功能适用的图片前提条件

- **必须是 PNG**：ComfyUI 的 Save Image 节点仅输出 PNG 并写入文本块；JPG/WebP 不含。
- **须由 ComfyUI 的 Save Image 节点直接生成**：使用不写元数据的第三方保存节点、或关闭了元数据写入，则无内容。
- **不能被外部重编码 / 编辑 / 压缩**：复制、改名安全；Photoshop / 预览另存、微信 QQ 压缩、拼图再导出都会丢失 `tEXt` 文本块。
- **元数据是「生成该图时」的工作流**，不代表当前 ComfyUI 编辑器的实时状态。
- 内嵌两路 JSON：`workflow`（编辑器格式，含节点坐标 / widget / 连线）与 `prompt`（API 格式，`class_type` + `inputs`，连线以 `[源节点, 输出序号]` 表示）。

---

## 工作原理

1. ComfyUI 把工作流序列化后写入 PNG 的 `tEXt` 文本块（键名 `workflow` / `prompt`）。
2. 本程序逐块解析 PNG 分块结构（`tEXt` / `iTXt` / `zTXt`），取出 JSON。
3. 前端把 JSON 归一化为四类视图：提示词、参数、节点、连接关系。
4. 桌面模式下，页面由本机回环 HTTP 服务（`127.0.0.1:随机端口`）提供，以避免 `file://` 路径编码问题；复制与写回文件通过 Python 桥接完成。

---

## 从源码构建

### 通用准备

```bash
python3 -m venv build_venv
source build_venv/bin/activate      # Windows: build_venv\Scripts\activate
pip install -r requirements.txt
```

### macOS（.app / .dmg / .pkg）

```bash
bash build.sh
```

产物：`dist/ComfyUI Workflow Extractor.app`、`ComfyUI-Workflow-Extractor-v1.1-macOS.dmg`、`ComfyUI-Workflow-Extractor-v1.1-macOS.pkg`

### Windows（单文件 EXE）

```bat
build_windows.bat
```

产物：`dist\ComfyUI-Workflow-Extractor.exe`、`ComfyUI-Workflow-Extractor-v1.1-Windows.zip`

### 浏览器模式（免安装）

```bash
python3 server.py
# 打开 http://localhost:8000/index.html
```

> 浏览器模式下写回原目录依赖 File System Access API（Chrome / Edge），其他浏览器退化为下载同名 `.json`。

---

## 目录结构

```
.
├── app.py                              # 桌面入口：pywebview 窗口 + PNG 解析 + 剪贴板/文件桥接
├── index.html                          # 界面（浏览器与桌面双模共用）
├── server.py                           # 浏览器模式的零依赖本地服务
├── requirements.txt
├── build.sh                            # macOS 打包（app + dmg + pkg）
├── build_windows.bat                   # Windows 打包（exe + zip）
├── ComfyUI Workflow Extractor.spec     # PyInstaller spec（macOS）
├── ComfyUI Workflow Extractor-windows.spec
├── cli/
│   └── comfyui_workflow_extractor.py   # 命令行版：批量提取，无需 GUI
├── packages/                           # 预编译分发包
│   ├── macos/
│   └── windows/
└── .github/workflows/build.yml         # CI：双平台自动构建
```

---

## 命令行版（可选）

```bash
python3 cli/comfyui_workflow_extractor.py --folder ~/ComfyUI/output   # 批量
python3 cli/comfyui_workflow_extractor.py a.png b.png                 # 指定文件
python3 cli/comfyui_workflow_extractor.py --check a.png               # 仅预览
```

---

## 已知限制

- 无法解析被重新编码过、或经通讯软件压缩传输的图片。
- macOS 应用未签名 / 未公证，首次启动需手动放行。
- Windows 包需系统具备 WebView2 Runtime。

---

## 许可证

MIT License，详见 [LICENSE](LICENSE)。
