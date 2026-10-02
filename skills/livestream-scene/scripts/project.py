"""Portable, non-destructive project bookkeeping. Semantic checks belong to the skill."""
import argparse
import json
import os
import hashlib
import shutil
import sys
import subprocess
from pathlib import Path
from PIL import Image, ImageOps

def default_root():
    config = Path(__file__).resolve().parents[1] / "project-settings.json"
    if config.exists():
        value = json.loads(config.read_text(encoding="utf-8"))["project_root"]
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError("安装项目路径配置无效，请用--root指定绝对项目目录")
        return Path(value)
    return Path.home() / "Documents" / "直播场景项目"

def location_links(path):
    path = Path(path).resolve()
    def link(label, target):
        value = target.as_posix().replace("<", "%3C").replace(">", "%3E")
        return f"[{label}](<{value}>)"
    return {"folder": link("打开结果文件夹", path),
            "image": link("下载第二版", path / "第二版.png"),
            "record": link("查看提示词与检查记录", path / "记录.md")}

def open_output(root, job, run):
    _, out = run_paths(root, job, run)
    if not out.is_dir():
        raise FileNotFoundError("结果文件夹不存在")
    if sys.platform == "win32":
        os.startfile(str(out))
    elif sys.platform == "darwin":
        subprocess.run(["open", str(out)], check=True)
    else:
        subprocess.run(["xdg-open", str(out)], check=True)
    return {"opened": str(out), "links": location_links(out)}

GUIDE = """直接在对话中发送场景参考（建议至少1张，可多张），提供品类、品牌或产品图之一。
品牌logo和特殊要求可选。素材整理、编号和文件管理由skill完成，无需手动放文件。
品牌/品类：
特殊要求：
附图并提出制作需求即可；也支持已有目录。
"""
def ingest(root, job, sources=(), request="", references=()):
    path = init_job(root, job)
    manifest = path / "素材清单.json"
    if manifest.is_symlink():
        raise ValueError("不接受清单符号链接")
    data = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {"files": [], "messages": []}
    known = {x["sha256"] for x in data["files"]}
    for item in sources:
        src = Path(item).resolve(strict=True)
        if not src.is_file():
            raise ValueError("附件不是文件")
        with Image.open(src) as im:
            im.verify()
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        if digest in known:
            continue
        dst = path / "参考" / (digest + src.suffix.lower())
        if dst.exists():
            if dst.is_symlink() or hashlib.sha256(dst.read_bytes()).hexdigest() != digest:
                raise FileExistsError(dst)
        else:
            shutil.copyfile(src, dst)
        data["files"].append({"sha256": digest, "original_name": src.name, "path": str(dst), "role": "由agent实际查看后识别"})
        known.add(digest)
    message = {"request": request, "references": list(references)}
    if (request or references) and message not in data["messages"]:
        data["messages"].append(message)
    atomic_json(manifest, data)
    return data
def number(value):
    if not str(value).isascii() or not str(value).isdigit() or int(value) < 1:
        raise ValueError("编号必须为正整数")
    return int(value)

def job_path(root, job):
    root = Path(root).resolve()
    path = root / f"{number(job):02d}"
    # Reuse legacy numeric folders without renaming user files.
    legacy = root / str(number(job))
    if legacy.exists() and not path.exists():
        path = legacy
    if path.is_symlink():
        raise ValueError("不接受项目编号目录符号链接")
    return path

def init_job(root, job=1):
    path = job_path(root, job)
    path.mkdir(parents=True, exist_ok=True)
    ref = path / "参考"
    if ref.is_symlink():
        raise ValueError("不接受参考目录符号链接")
    ref.mkdir(exist_ok=True)
    req = path / "需求.txt"
    if not req.exists():
        with req.open("x", encoding="utf-8") as f:
            f.write(GUIDE)
    return path

def scan(root, job):
    path = job_path(root, job)
    result = []
    for p in sorted(path.rglob("*")):
        if p.is_file() and not any(x in {"结果", ".工作记录"} for x in p.relative_to(path).parts):
            if p.is_symlink():
                continue
            result.append(str(p.resolve()))
    return result

def atomic_json(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)

def run_paths(root, job, run):
    path = job_path(root, job)
    run = number(run)
    work = path / ".工作记录" / f"run-{run:03d}"
    out = path / "结果" / f"run-{run:03d}"
    for p in (path / ".工作记录", path / "结果", work, out):
        if p.is_symlink():
            raise ValueError("不接受工作或结果目录符号链接")
    return work, out

def begin(root, job):
    path = init_job(root, job)
    n = 1
    while any(p.exists() for p in run_paths(root, job, n)):
        n += 1
    work, out = run_paths(root, job, n)
    work.mkdir(parents=True)
    out.mkdir(parents=True)
    atomic_json(work / "state.json", {"run": n, "status": "running", "rounds": {}})
    return {"run": n, "work": str(work), "output": str(out)}

def status(root, job, run):
    work, _ = run_paths(root, job, run)
    return json.loads((work / "state.json").read_text(encoding="utf-8"))

def save(root, job, run, round_no, source, width=1080, height=1920, replace=False):
    if round_no not in (1, 2) or min(width, height) < 1:
        raise ValueError("轮次必须是1或2，尺寸必须为正")
    work, out = run_paths(root, job, run)
    state = status(root, job, run)
    if state["status"] == "complete":
        raise ValueError("已完成run不能修改，请建立新run")
    if round_no == 2 and "1" not in state["rounds"]:
        raise ValueError("先登记第一轮")
    prompt = work / f"prompt-{round_no}.txt"
    if not prompt.exists() or not prompt.read_text(encoding="utf-8").strip():
        raise ValueError("缺少完整提示词")
    target = out / ("第一版.png" if round_no == 1 else "第二版.png")
    if target.exists() and not replace:
        raise FileExistsError(target)
    if replace and round_no != 2:
        raise ValueError("仅第二轮质量修正可显式替换")
    source = Path(source).resolve()
    if source == target.resolve():
        raise ValueError("输入不可为交付文件本身")
    with Image.open(source) as raw:
        im = ImageOps.exif_transpose(raw)
        im.load()
        size = im.size
        if abs(size[0] / size[1] / (width / height) - 1) > 0.02:
            raise ValueError("源图与目标比例相差超过2%，请先检查构图，不强行拉伸")
        original = work / f"round-{round_no}-source.png"
        if original.exists():
            k = 1
            while (work / f"round-{round_no}-source-{k}.png").exists():
                k += 1
            original = work / f"round-{round_no}-source-{k}.png"
        im.save(original)
        tmp = out / f".round-{round_no}.tmp.png"
        im.resize((width, height), Image.Resampling.LANCZOS).save(tmp)
        os.replace(tmp, target)
    state["rounds"][str(round_no)] = {"source": str(original), "source_size": list(size),
                                     "output": str(target), "output_size": [width, height],
                                     "normalization": "Lanczos resize without crop"}
    atomic_json(work / "state.json", state)
    return state

def finish(root, job, run):
    work, out = run_paths(root, job, run)
    state = status(root, job, run)
    if set(state["rounds"]) != {"1", "2"}:
        raise ValueError("两轮图片未齐全")
    texts = []
    for name in ("prompt-1.txt", "prompt-2.txt", "review.md"):
        p = work / name
        if not p.exists() or not p.read_text(encoding="utf-8").strip():
            raise ValueError(f"缺少记录：{name}")
        texts.append(f"## {name}\n\n" + p.read_text(encoding="utf-8"))
    for data in state["rounds"].values():
        with Image.open(data["output"]) as im:
            if list(im.size) != data["output_size"]:
                raise ValueError("实际交付尺寸与记录不同")
    report = out / "记录.md"
    content = "\n\n".join(texts) + "\n\n## 尺寸记录\n\n" + json.dumps(state["rounds"], ensure_ascii=False, indent=2)
    if not report.exists():
        with report.open("x", encoding="utf-8") as f:
            f.write(content)
    elif state["status"] != "complete":
        raise FileExistsError(report)
    state["status"] = "complete"
    atomic_json(work / "state.json", state)
    nxt = init_job(root, number(job) + 1)
    return {"output": str(out), "next": str(nxt), "status": "complete", "links": location_links(out)}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["init", "ingest", "scan", "begin", "status", "save", "finish", "open"])
    p.add_argument("--root", default=str(default_root()))
    p.add_argument("--job", default="1")
    p.add_argument("--run", type=int)
    p.add_argument("--round", type=int, dest="round_no")
    p.add_argument("--source")
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.add_argument("--replace", action="store_true")
    p.add_argument("--sources", nargs="*", default=[])
    p.add_argument("--request", default="")
    p.add_argument("--references", nargs="*", default=[])
    a = p.parse_args()
    if a.command in {"status", "save", "finish", "open"} and a.run is None:
        p.error("--run required")
    if a.command == "save" and (a.round_no is None or a.source is None):
        p.error("--round and --source required")
    if a.command == "init":
        result = {"job": str(init_job(a.root, a.job)), "guide": GUIDE}
    elif a.command == "ingest":
        result = ingest(a.root, a.job, a.sources, a.request, a.references)
    elif a.command == "scan":
        result = scan(a.root, a.job)
    elif a.command == "begin":
        result = begin(a.root, a.job)
    elif a.command == "status":
        result = status(a.root, a.job, a.run)
    elif a.command == "save":
        result = save(a.root, a.job, a.run, a.round_no, a.source, a.width, a.height, a.replace)
    elif a.command == "open":
        result = open_output(a.root, a.job, a.run)
    else:
        result = finish(a.root, a.job, a.run)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
