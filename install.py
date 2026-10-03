"""Install or explicitly upgrade a local skill with a recoverable backup."""
import argparse
import importlib.util
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

def default_skills_dir():
    canonical = Path.home() / ".agents" / "skills"
    legacy = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "skills"
    # Keep an existing installation in its observed location; new installs use current docs.
    if (canonical / "livestream-scene").exists():
        return canonical
    if (legacy / "livestream-scene").exists():
        return legacy
    return canonical

def install(skills_dir, project_root=None, upgrade=False):
    source = Path(__file__).resolve().parent / "skills" / "livestream-scene"
    target = Path(skills_dir).expanduser().resolve() / source.name
    if target.is_symlink():
        raise ValueError("不升级符号链接技能目录，请使用其实际安装路径")
    if target.exists() and not upgrade:
        raise FileExistsError(f"技能已存在：{target}；使用--upgrade会先备份再升级")
    config = target / "project-settings.json"
    if config.is_symlink():
        raise ValueError("不接受配置符号链接")
    if project_root is None and config.exists():
        project_root = json.loads(config.read_text(encoding="utf-8"))["project_root"]
    project_root = Path(project_root or Path.home() / "Documents" / "直播场景项目").expanduser().resolve()
    if project_root == target or target in project_root.parents:
        raise ValueError("项目目录不能位于技能安装目录内")
    spec = importlib.util.spec_from_file_location("scene_project", source / "scripts" / "project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    job = module.init_job(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "project-settings.json")
    if target.exists():
        # Backups live outside the skill discovery directory.
        backup = target.parent.parent / "skill-backups" / ("livestream-scene-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8])
        shutil.copytree(target, backup, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        print(f"旧版备份：{backup}")
    shutil.copytree(source, target, dirs_exist_ok=upgrade, ignore=ignore)
    config.write_text(json.dumps({"project_root": str(project_root)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return target, job

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--project-root", help="可选：更改生成结果的项目根目录")
    p.add_argument("--skills-dir", default=str(default_skills_dir()))
    p.add_argument("--upgrade", action="store_true", help="先备份已安装技能，再更新本包文件")
    a = p.parse_args()
    print("使用前提：本项目以ChatGPT为首选并围绕其生图能力优化；必须使用具备生图能力的对话型AI。安装本包不会获得生图服务或权限，宿主还需支持本地技能、看图与文件读写。")
    try:
        target, job = install(a.skills_dir, a.project_root, a.upgrade)
    except (OSError, ValueError, KeyError, ImportError) as e:
        p.exit(1, f"安装未完成：{e}\n需要Python 3.10+和Pillow；请先运行 python -m pip install -r requirements.txt\n")
    print(f"安装成功：{target}\n结果保存在：{job.parent}/<编号>/结果/run-<运行编号>/")
    print(f"[打开项目文件夹](<{job.parent.as_posix()}>)")
    print("下一轮对话调用 $livestream-scene；若未发现技能，重启宿主。")
    print("直接在对话中发送参考图和品类/品牌/产品图；logo与特殊要求可选。素材与结果由技能管理，完成后会给出可点击的结果文件夹、图片和记录链接。")
