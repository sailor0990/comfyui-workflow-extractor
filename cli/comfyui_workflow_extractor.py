#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ComfyUI 工作流提取器
====================
从 ComfyUI 生成的 PNG 图片中还原内嵌的工作流（节点 / 提示词 / 连接 / 参数）。

原理
----
ComfyUI 的 Save Image 节点会把工作流以 PNG 文本块(tEXt/iTXt/zTXt)的形式写进图片：
  - "workflow" : 编辑器完整格式（含节点坐标、widget、连线），拖回 ComfyUI 即复原界面
  - "prompt"   : API 格式（class_type + inputs，连线用 [源节点, 输出序号] 表示），同样可加载执行
两者都是 JSON。本工具直接解析 PNG 块，不依赖 PIL，跨平台可运行。

用法
----
  1) 双击 / 命令行直接运行（弹出选图对话框）：
        python3 comfyui_workflow_extractor.py
  2) 命令行指定文件（可多个）：
        python3 comfyui_workflow_extractor.py a.png b.png
  3) 批量处理整个目录（含子目录）：
        python3 comfyui_workflow_extractor.py --folder ~/ComfyUI/output
  4) 仅检查不写出（看看图片里有什么）：
        python3 comfyui_workflow_extractor.py --check a.png

输出
----
选中图片  ~/some/photo.png  会在同目录生成：
  - photo.json      最佳可用工作流（优先 workflow 块，否则用 prompt 块）
  - photo.api.json  若存在 workflow 块，额外再导出 API 格式（prompt 块）
文件名冲突时自动追加 .1 / .2 后缀，不覆盖原文件。
"""

import os
import sys
import json
import struct
import zlib
import subprocess

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TEXT_CHUNK_TYPES = (b"tEXt", b"iTXt", b"zTXt")


# --------------------------------------------------------------------------
# 核心：读取 PNG 中所有文本块
# --------------------------------------------------------------------------
def read_png_text_chunks(path):
    """返回 {关键字: 解码后的文本值}，仅解析 tEXt/iTXt/zTXt 三类文本块。"""
    chunks = {}
    with open(path, "rb") as f:
        if f.read(8) != PNG_SIGNATURE:
            raise ValueError("不是合法的 PNG 文件（缺少 PNG 签名）")
        while True:
            header = f.read(8)
            if len(header) < 8:
                break  # 文件异常截断
            length = struct.unpack(">I", header[:4])[0]
            chunk_type = header[4:8]
            data = f.read(length)
            f.read(4)  # CRC，跳过
            if chunk_type in TEXT_CHUNK_TYPES:
                key, value = _parse_text_chunk(chunk_type, data)
                if key:
                    chunks[key] = value
            if chunk_type == b"IEND":
                break
    return chunks


def _parse_text_chunk(chunk_type, data):
    """解析单个文本块，返回 (关键字, 文本)。失败返回 (None, None)。"""
    if chunk_type == b"tEXt":
        # keyword \0 text  (Latin-1)
        i = data.find(b"\x00")
        if i == -1:
            return None, None
        keyword = data[:i].decode("latin-1")
        text = data[i + 1:].decode("utf-8", errors="replace")
        return keyword, text

    if chunk_type == b"zTXt":
        # keyword \0 压缩方法(1字节) zlib数据
        i = data.find(b"\x00")
        if i == -1:
            return None, None
        keyword = data[:i].decode("latin-1")
        compressed = data[i + 2:]  # 跳过压缩方法字节
        try:
            text = zlib.decompress(compressed).decode("utf-8", errors="replace")
        except zlib.error:
            return None, None
        return keyword, text

    if chunk_type == b"iTXt":
        # keyword \0 压缩标志(1) 压缩方法(1) 语言标签\0 翻译关键词\0 文本
        i = data.find(b"\x00")
        if i == -1:
            return None, None
        keyword = data[:i].decode("latin-1")
        rest = data[i + 1:]
        if len(rest) < 2:
            return None, None
        comp_flag = rest[0]
        j = rest.find(b"\x00", 2)        # 语言标签结束
        if j == -1:
            return None, None
        k = rest.find(b"\x00", j + 1)    # 翻译关键词结束
        if k == -1:
            return None, None
        text_bytes = rest[k + 1:]
        if comp_flag == 1:
            try:
                text_bytes = zlib.decompress(text_bytes)
            except zlib.error:
                return None, None
        return keyword, text_bytes.decode("utf-8", errors="replace")

    return None, None


# --------------------------------------------------------------------------
# 提取并写出
# --------------------------------------------------------------------------
def _safe_path(directory, stem, suffix):
    """生成不冲突的输出路径；已存在则追加 .1/.2 后缀。"""
    cand = os.path.join(directory, stem + suffix)
    if not os.path.exists(cand):
        return cand
    n = 1
    while True:
        cand = os.path.join(directory, f"{stem}{suffix}.{n}")
        if not os.path.exists(cand):
            return cand
        n += 1


def _summary_of(obj, kind):
    """给工作流对象生成一句话摘要，便于终端反馈。"""
    if kind == "workflow":
        nodes = obj.get("nodes", [])
        links = obj.get("links", [])
        return f"编辑器格式 | 节点 {len(nodes)} 个 | 连线 {len(links)} 条"
    else:  # api / prompt
        return f"API 格式 | 节点 {len(obj)} 个"


def extract_one(path, do_write=True, verbose=True):
    """提取单张图片。返回 dict 结果。"""
    result = {
        "path": path,
        "error": None,
        "workflow_file": None,
        "api_file": None,
        "has_workflow": False,
        "has_prompt": False,
    }
    try:
        chunks = read_png_text_chunks(path)
    except Exception as e:
        result["error"] = f"读取失败：{e}"
        if verbose:
            print(f"  ✗ {os.path.basename(path)}: {result['error']}")
        return result

    wf_raw = chunks.get("workflow")
    pr_raw = chunks.get("prompt")
    result["has_workflow"] = wf_raw is not None
    result["has_prompt"] = pr_raw is not None

    if wf_raw is None and pr_raw is None:
        result["error"] = "该图片未内嵌任何 ComfyUI 工作流（可能是外部编辑/重编码过的图）"
        if verbose:
            print(f"  ⊘ {os.path.basename(path)}: {result['error']}")
        return result

    directory = os.path.dirname(os.path.abspath(path))
    stem = os.path.splitext(os.path.basename(path))[0]

    # 优先 workflow 块作为主输出；否则用 prompt 块
    primary_raw = wf_raw if wf_raw is not None else pr_raw
    primary_kind = "workflow" if wf_raw is not None else "api"

    if do_write:
        try:
            obj = json.loads(primary_raw)
            out_path = _safe_path(directory, stem, ".json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
            result["workflow_file"] = out_path
        except Exception as e:
            result["error"] = f"JSON 解析/写出失败：{e}"

        # 仅当 workflow 与 prompt 块同时存在时，才额外导出 API 格式，
        # 避免“只有 prompt 块”时 .json 与 .api.json 内容重复。
        if pr_raw is not None and wf_raw is not None:
            try:
                obj2 = json.loads(pr_raw)
                api_path = _safe_path(directory, stem, ".api.json")
                with open(api_path, "w", encoding="utf-8") as f:
                    json.dump(obj2, f, ensure_ascii=False, indent=2)
                result["api_file"] = api_path
            except Exception:
                pass

    if verbose:
        if result["error"]:
            print(f"  ✗ {os.path.basename(path)}: {result['error']}")
        else:
            tag = "编辑器格式" if primary_kind == "workflow" else "API 格式"
            print(f"  ✓ {os.path.basename(path)}  [{tag}]")
            if result["workflow_file"]:
                print(f"      → {result['workflow_file']}")
            if result["api_file"]:
                print(f"      → {result['api_file']}  (API 格式)")
    return result


# --------------------------------------------------------------------------
# 文件选择：tkinter，macOS 回退原生对话框
# --------------------------------------------------------------------------
def pick_files_tkinter():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.update()
    files = filedialog.askopenfilenames(
        title="选择 ComfyUI 生成的 PNG 图片（可多选）",
        filetypes=[("PNG 图片", "*.png"), ("所有文件", "*.*")],
    )
    root.destroy()
    return list(files)


def pick_files_osascript():
    script = (
        'set chosen to choose file with prompt "选择 ComfyUI 生成的 PNG 图片（可多选）" '
        'of type {"public.png"} with multiple selections allowed\n'
        'set output to ""\n'
        'repeat with f in chosen\n'
        '    set output to output & (POSIX path of f) & linefeed\n'
        'end repeat\n'
        'return output\n'
    )
    proc = subprocess.run(["osascript", "-e", script],
                         capture_output=True, text=True)
    if proc.returncode != 0:
        return []
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def pick_files():
    try:
        files = pick_files_tkinter()
        if files:
            return files
    except Exception:
        pass
    if sys.platform == "darwin":
        try:
            return pick_files_osascript()
        except Exception:
            return []
    return []


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main(argv):
    files = []
    check_only = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(__doc__)
            return 0
        elif a == "--check":
            check_only = True
        elif a == "--folder":
            i += 1
            folder = argv[i] if i < len(argv) else "."
            for root, _, names in os.walk(folder):
                for n in names:
                    if n.lower().endswith(".png"):
                        files.append(os.path.join(root, n))
        else:
            files.append(a)
        i += 1

    if not files:
        print("请选择要提取工作流的 PNG 图片……")
        files = pick_files()
        if not files:
            print("未选择任何文件，已退出。")
            return 0

    total = len(files)
    ok = 0
    skipped = 0
    failed = 0
    print(f"共 {total} 张图片，开始提取……\n")
    for p in files:
        if not os.path.isfile(p):
            print(f"  ✗ 找不到文件：{p}")
            failed += 1
            continue
        r = extract_one(p, do_write=not check_only)
        if r["error"]:
            if "未内嵌" in (r["error"] or ""):
                skipped += 1
            else:
                failed += 1
        else:
            ok += 1
    print(f"\n完成：成功 {ok} | 无内嵌工作流 {skipped} | 失败 {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
