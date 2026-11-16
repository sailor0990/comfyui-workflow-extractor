#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ComfyUI 工作流提取器 · 桌面应用入口
====================================
使用 pywebview 打开本地 index.html（原生 macOS WebView 窗口），
并通过 JS ↔ Python 桥接实现：
  - open_files()   : 调用原生 macOS 打开对话框，读取并解析 PNG 内嵌工作流
  - save_next_to() : 把同名 .json 直接写回图片原目录

v2 修复（白屏根因）：
  旧版以 `url="file://" + HTML_PATH` 加载页面。打包后的 .app 名为
  "ComfyUI Workflow Extractor.app"，路径中含空格，file:// URL 未做百分号编码，
  WKWebView 会把 URL 截断在空格处（file:///Applications/ComfyUI），文件不存在，
  于是窗口空白且无任何错误提示。
  现改为：在本机回环地址起一个临时 HTTP 服务提供 index.html，
  彻底绕开 file:// 的路径编码与 WKWebView 本地文件限制；HTTP 不可用时回退到
  正确编码的 as_uri()。同时写入启动日志，便于日后诊断。

打包：见 build.sh（PyInstaller → .app → .dmg / .pkg）
"""
import os
import sys
import json
import struct
import zlib
import threading
import functools
import traceback
import subprocess
import http.server
import socketserver
import pathlib
import datetime

VERSION = "1.1"

import webview

try:  # pywebview >= 5 推荐 FileDialog；旧版回退到模块常量
    from webview import FileDialog as _FileDialog
    _OPEN_DIALOG = _FileDialog.OPEN
except Exception:  # pragma: no cover
    _OPEN_DIALOG = webview.OPEN_DIALOG


# --------------------------------------------------------------------------
# 日志（打包后 console=False，日志落到文件，便于排查白屏类问题）
# --------------------------------------------------------------------------
def _log_dir():
    cand = os.path.expanduser("~/Library/Logs/ComfyUIWorkflowExtractor")
    try:
        os.makedirs(cand, exist_ok=True)
        return cand
    except Exception:
        import tempfile
        return tempfile.gettempdir()


LOG_PATH = os.path.join(_log_dir(), "app.log")


def log(msg):
    line = f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


# --------------------------------------------------------------------------
# 资源定位：打包后 _MEIPASS(Frameworks) / Contents/Resources / 脚本目录，逐个尝试
# --------------------------------------------------------------------------
def _candidate_dirs():
    dirs = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(meipass)
        # .app/Contents/Resources 兜底（BUNDLE 结构）
        try:
            dirs.append(os.path.join(os.path.dirname(os.path.dirname(meipass)), "Resources"))
        except Exception:
            pass
    here = os.path.dirname(os.path.abspath(__file__))
    dirs.append(here)
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    dirs.append(exe_dir)
    try:
        dirs.append(os.path.join(os.path.dirname(os.path.dirname(exe_dir)), "Resources"))
    except Exception:
        pass
    out, seen = [], set()
    for d in dirs:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def find_html():
    for d in _candidate_dirs():
        p = os.path.join(d, "index.html")
        if os.path.isfile(p):
            return p
    return None


HTML_PATH = find_html()


# --------------------------------------------------------------------------
# 本地回环 HTTP 服务（用于加载页面，避开 file:// 路径编码问题）
# --------------------------------------------------------------------------
class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 静音访问日志
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def start_local_server(directory):
    handler = functools.partial(_QuietHandler, directory=directory)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    socketserver.ThreadingTCPServer.daemon_threads = True
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    log(f"本地 HTTP 服务已启动: 127.0.0.1:{port} -> {directory}")
    return httpd, port


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TEXT_CHUNK_TYPES = (b"tEXt", b"iTXt", b"zTXt")


# --------------------------------------------------------------------------
# PNG 文本块解析（与浏览器内 JS 逻辑一致，Python 实现）
# --------------------------------------------------------------------------
def read_png_text_chunks(path):
    chunks = {}
    with open(path, "rb") as f:
        if f.read(8) != PNG_SIGNATURE:
            raise ValueError("不是合法的 PNG 文件")
        while True:
            header = f.read(8)
            if len(header) < 8:
                break
            length = struct.unpack(">I", header[:4])[0]
            ctype = header[4:8]
            data = f.read(length)
            f.read(4)  # CRC
            if ctype in TEXT_CHUNK_TYPES:
                key, value = _parse_text_chunk(ctype, data)
                if key:
                    chunks[key] = value
            if ctype == b"IEND":
                break
    return chunks


def _parse_text_chunk(ctype, data):
    if ctype == b"tEXt":
        i = data.find(b"\x00")
        if i == -1:
            return None, None
        return data[:i].decode("latin-1"), data[i + 1:].decode("utf-8", "replace")
    if ctype == b"zTXt":
        i = data.find(b"\x00")
        if i == -1:
            return None, None
        try:
            return data[:i].decode("latin-1"), zlib.decompress(data[i + 2:]).decode("utf-8", "replace")
        except Exception:
            return None, None
    if ctype == b"iTXt":
        i = data.find(b"\x00")
        if i == -1:
            return None, None
        rest = data[i + 1:]
        if len(rest) < 2:
            return None, None
        comp_flag = rest[0]
        j = rest.find(b"\x00", 2)
        if j == -1:
            return None, None
        k = rest.find(b"\x00", j + 1)
        if k == -1:
            return None, None
        tb = rest[k + 1:]
        if comp_flag == 1:
            try:
                tb = zlib.decompress(tb)
            except Exception:
                return None, None
        return data[:i].decode("latin-1"), tb.decode("utf-8", "replace")
    return None, None


def _safe_path(directory, stem, suffix):
    cand = os.path.join(directory, stem + suffix)
    if not os.path.exists(cand):
        return cand
    n = 1
    while True:
        cand = os.path.join(directory, f"{stem}{suffix}.{n}")
        if not os.path.exists(cand):
            return cand
        n += 1


def extract(path):
    rec = {
        "fileName": os.path.basename(path),
        "baseName": os.path.splitext(os.path.basename(path))[0],
        "format": "none",
        "workflowObj": None,
        "promptObj": None,
        "error": None,
        "originalPath": path,
    }
    try:
        chunks = read_png_text_chunks(path)
    except Exception as e:
        rec["error"] = f"读取失败：{e}"
        return rec
    wf = chunks.get("workflow")
    pr = chunks.get("prompt")
    try:
        if wf:
            rec["workflowObj"] = json.loads(wf)
    except Exception as e:
        rec["error"] = f"workflow 块 JSON 解析失败：{e}"
    try:
        if pr:
            rec["promptObj"] = json.loads(pr)
    except Exception as e:
        if not rec["error"]:
            rec["error"] = f"prompt 块 JSON 解析失败：{e}"
    if rec["workflowObj"] and rec["promptObj"]:
        rec["format"] = "both"
    elif rec["workflowObj"]:
        rec["format"] = "workflow"
    elif rec["promptObj"]:
        rec["format"] = "api"
    else:
        if not rec["error"]:
            rec["error"] = "该图片未内嵌任何 ComfyUI 工作流（可能为外部编辑/重编码过的图）"
    return rec


# --------------------------------------------------------------------------
# 跨平台系统剪贴板写入（JS Clipboard API 不可用时的兜底通道）
# --------------------------------------------------------------------------
def clipboard_copy(text):
    """把文本写入系统剪贴板。返回 (ok: bool, error: str|None)。"""
    data = text.encode("utf-8")
    if sys.platform == "darwin":
        try:
            p = subprocess.run(["pbcopy"], input=data,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if p.returncode == 0:
                return True, None
            return False, (p.stderr or b"").decode("utf-8", "replace") or "pbcopy 执行失败"
        except Exception as e:
            return False, str(e)

    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            CF_UNICODETEXT = 13
            GMEM_MOVEABLE = 0x0002
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
            kernel32.GlobalLock.restype = wintypes.LPVOID
            kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
            kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
            user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]

            buf = ctypes.create_unicode_buffer(text)
            size = ctypes.sizeof(buf)
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
            if not handle:
                return False, "GlobalAlloc 失败"
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                kernel32.GlobalFree(handle)
                return False, "GlobalLock 失败"
            ctypes.memmove(ptr, buf, size)
            kernel32.GlobalUnlock(handle)

            if not user32.OpenClipboard(None):
                kernel32.GlobalFree(handle)
                return False, "OpenClipboard 失败"
            try:
                user32.EmptyClipboard()
                if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                    kernel32.GlobalFree(handle)
                    return False, "SetClipboardData 失败"
                # 成功后内存所有权移交系统，不可再 GlobalFree
            finally:
                user32.CloseClipboard()
            return True, None
        except Exception as e:
            return False, str(e)

    # Linux / 其他平台
    for cmd in (["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
                ["wl-copy"]):
        try:
            p = subprocess.run(cmd, input=data,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if p.returncode == 0:
                return True, None
        except FileNotFoundError:
            continue
        except Exception:
            continue
    return False, "未找到可用的剪贴板工具"


# --------------------------------------------------------------------------
# JS ↔ Python 桥接
# --------------------------------------------------------------------------
class Api:
    def __init__(self):
        self._window = None

    def _win(self):
        if self._window is not None:
            return self._window
        try:
            return webview.active_window()
        except Exception:
            return None

    def version(self):
        return VERSION

    def copy_to_clipboard(self, text):
        """供页面各分区复制按钮使用的剪贴板兜底通道。"""
        try:
            ok, err = clipboard_copy("" if text is None else str(text))
            if not ok:
                log(f"copy_to_clipboard 失败: {err}")
            else:
                log(f"copy_to_clipboard 成功: {len(str(text))} 字符")
            return {"ok": bool(ok), "error": err}
        except Exception as e:
            log(f"copy_to_clipboard 异常: {e}")
            return {"ok": False, "error": str(e)}

    def ui_ready(self):
        """页面渲染完成后由 JS 回调，确认界面已加载（用于日志确认，不再白屏）。"""
        log("UI ready: 页面已成功渲染")
        return True

    def open_files(self):
        win = self._win()
        if win is None:
            log("open_files: 无法获取窗口")
            return []
        try:
            paths = win.create_file_dialog(
                _OPEN_DIALOG,
                allow_multiple=True,
                file_types=("PNG 图片 (*.png)", "*.png"),
            )
        except Exception as e:
            log(f"open_files 对话框异常: {e}")
            try:
                paths = win.create_file_dialog(_OPEN_DIALOG, allow_multiple=True)
            except Exception as e2:
                log(f"open_files 二次尝试失败: {e2}")
                return []
        if not paths:
            return []
        results = []
        for p in paths:
            try:
                results.append(extract(p))
            except Exception as e:
                log(f"extract 失败 {p}: {e}")
        log(f"open_files: 已解析 {len(results)} 张图片")
        return results

    def save_next_to(self, original_path, base_name, content, api_content=None):
        try:
            directory = os.path.dirname(os.path.abspath(original_path))
            written = []
            p = _safe_path(directory, base_name, ".json")
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            written.append(os.path.basename(p))
            if api_content:
                p2 = _safe_path(directory, base_name, ".api.json")
                with open(p2, "w", encoding="utf-8") as f:
                    f.write(api_content)
                written.append(os.path.basename(p2))
            log(f"save_next_to: 已写入 {written} -> {directory}")
            return {"ok": True, "files": written}
        except Exception as e:
            log(f"save_next_to 失败: {e}")
            return {"ok": False, "error": str(e)}


def main():
    log("=" * 60)
    log(f"ComfyUI 工作流提取器 v{VERSION} 启动。frozen={getattr(sys, 'frozen', False)} _MEIPASS={getattr(sys, '_MEIPASS', None)}")
    log(f"HTML_PATH={HTML_PATH}")

    if not HTML_PATH:
        log("致命错误：找不到 index.html，窗口将空白。已搜索: " + str(_candidate_dirs()))
        # 仍然起窗口显示错误，避免"纯白无提示"
        webview.create_window(
            f"ComfyUI 工作流提取器 v{VERSION}",
            html="<h2 style='font-family:-apple-system'>index.html 缺失</h2>"
                 "<p>应用资源损坏，请重新安装。</p>",
            width=900, height=600,
        )
        webview.start()
        return

    api = Api()

    # 首选：本地回环 HTTP 服务（无 file:// 路径编码问题）
    url = None
    httpd = None
    try:
        httpd, port = start_local_server(os.path.dirname(HTML_PATH))
        url = f"http://127.0.0.1:{port}/{os.path.basename(HTML_PATH)}"
        log(f"页面 URL(HTTP): {url}")
    except Exception as e:
        log(f"HTTP 服务启动失败，回退 file URI: {e}")
        url = pathlib.Path(HTML_PATH).resolve().as_uri()
        log(f"页面 URL(file): {url}")

    window = webview.create_window(
        f"ComfyUI 工作流提取器 v{VERSION}",
        url=url,
        js_api=api,
        width=1080,
        height=820,
        min_size=(900, 640),
    )
    api._window = window

    try:
        webview.start()
    except Exception:
        log("webview.start 异常:\n" + traceback.format_exc())
        raise
    finally:
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:
                pass
        log("退出。")


if __name__ == "__main__":
    main()
