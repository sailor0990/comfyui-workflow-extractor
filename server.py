#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ComfyUI 工作流提取器 · 本地服务
==============================
仅用 Python 标准库，把交互式页面托管在 http://localhost:8000，
以便浏览器在「安全上下文」下使用文件系统 API，直接把工作流写回图片原目录。

启动：
    python3 server.py
然后浏览器会自动打开 http://localhost:8000/index.html
按 Ctrl+C 停止。
"""
import os
import sys
import webbrowser
import socketserver
import http.server

PORT = 8000
ROOT = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, fmt, *args):
        pass  # 静默日志


def main():
    os.chdir(ROOT)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        url = f"http://localhost:{PORT}/index.html"
        print(f"ComfyUI 工作流提取器已启动：{url}")
        print("（用 Chrome / Edge 打开可把工作流直接写回图片原目录；其他浏览器将下载同名文件）")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止服务。")


if __name__ == "__main__":
    main()
