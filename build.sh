#!/usr/bin/env bash
# ComfyUI 工作流提取器 · macOS 打包脚本 (v1.1)
# 依赖：build_venv 中已安装 pywebview + pyinstaller
set -e
cd "$(dirname "$0")"

APP_NAME="ComfyUI Workflow Extractor"
BUNDLE_ID="com.comfyui.workflow-extractor"
VERSION="1.1"
VENV="build_venv"
DMG="ComfyUI-Workflow-Extractor-v${VERSION}-macOS.dmg"
PKG="ComfyUI-Workflow-Extractor-v${VERSION}-macOS.pkg"

if [ ! -d "$VENV" ]; then
  echo "未找到 $VENV，请先创建并安装依赖："
  echo "  python3 -m venv $VENV && $VENV/bin/pip install pywebview pyinstaller"
  exit 1
fi
source "$VENV/bin/activate"

echo "==> 0/5 清理旧产物（移走而非批量删除）"
python - <<'PY'
import shutil, os, glob, tempfile, time
trash = os.path.join(tempfile.gettempdir(), "cwfe_old_" + time.strftime("%Y%m%d-%H%M%S"))
os.makedirs(trash, exist_ok=True)
for p in ["build", "dist"]:
    if os.path.isdir(p):
        shutil.move(p, os.path.join(trash, os.path.basename(p)))
        print(f"  已移走旧目录 {p} -> {trash}")
for pat in ["*.dmg", "*.pkg"]:
    for f in glob.glob(pat):
        os.remove(f); print(f"  已删除旧包 {f}")
PY

echo "==> 1/5 PyInstaller 打包 .app（v${VERSION}）"
pyinstaller --noconfirm --clean "${APP_NAME}.spec"

echo "==> 2/5 校验产物完整性"
test -x "dist/${APP_NAME}.app/Contents/MacOS/${APP_NAME}" || { echo "可执行缺失"; exit 1; }
find "dist/${APP_NAME}.app" -name index.html -print -quit | grep -q . || { echo "index.html 未打入"; exit 1; }
PLIST="dist/${APP_NAME}.app/Contents/Info.plist"
echo "  CFBundleShortVersionString = $(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$PLIST" 2>/dev/null)"

echo "==> 3/5 生成 ${DMG}（拖拽安装）"
DMGROOT="$(mktemp -d)"
cp -R "dist/$APP_NAME.app" "$DMGROOT/"
ln -sf /Applications "$DMGROOT/Applications"
hdiutil create -volname "$APP_NAME" -srcfolder "$DMGROOT" -ov -format UDZO "$DMG" >/dev/null
echo "  临时目录 $DMGROOT（系统会自行清理）"

echo "==> 4/5 生成 ${PKG}（标准安装向导）"
productbuild --component "dist/$APP_NAME.app" /Applications "$PKG" 2>&1 | grep -v "Permission denied" || true

echo "==> 5/5 完成"
ls -lh "$DMG" "$PKG"
du -sh "dist/$APP_NAME.app"
echo
echo "分发方式："
echo "  - $DMG  ：双击挂载后把 App 拖到 应用程序"
echo "  - $PKG  ：双击走标准安装向导，安装到 /Applications"
