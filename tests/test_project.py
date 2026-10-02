import importlib.util
import tempfile
import unittest
from unittest.mock import patch
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
m = load("project", ROOT / "skills/livestream-scene/scripts/project.py")
installer = load("installer", ROOT / "install.py")

class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "中文 项目"
    def setup_run(self):
        info = m.begin(self.root, 1)
        work = Path(info["work"])
        for n in (1, 2):
            (work / f"prompt-{n}.txt").write_text("完整提示词", encoding="utf-8")
        (work / "review.md").write_text("实际检查记录", encoding="utf-8")
        src = Path(self.tmp.name) / "source.png"
        Image.new("RGB", (90, 160), "white").save(src)
        return info, src
    def test_init_preserves_materials_and_requests(self):
        job = m.init_job(self.root)
        (job / "需求.txt").write_text("我的需求", encoding="utf-8")
        (job / "参考/a.txt").write_text("素材", encoding="utf-8")
        m.init_job(self.root)
        self.assertEqual((job / "需求.txt").read_text(encoding="utf-8"), "我的需求")
        self.assertEqual(len(m.scan(self.root, 1)), 2)
    def test_two_outputs_resume_and_finish(self):
        info, src = self.setup_run()
        m.save(self.root, 1, info["run"], 1, src)
        self.assertEqual(set(m.status(self.root, 1, info["run"])["rounds"]), {"1"})
        with self.assertRaises(FileExistsError):
            m.save(self.root, 1, info["run"], 1, src)
        m.save(self.root, 1, info["run"], 2, src)
        result = m.finish(self.root, 1, info["run"])
        self.assertEqual(len(list(Path(result["output"]).glob("*.png"))), 2)
        self.assertTrue(Path(result["next"]).is_dir())
        m.finish(self.root, 1, info["run"])
        self.assertEqual(m.begin(self.root, 1)["run"], 2)
    def test_reject_bad_aspect_and_incomplete(self):
        info, src = self.setup_run()
        Image.new("RGB", (100, 100)).save(src)
        with self.assertRaises(ValueError):
            m.save(self.root, 1, 1, 1, src)
        with self.assertRaises(ValueError):
            m.finish(self.root, 1, 1)
    def test_round_order_and_corrective_save(self):
        info, src = self.setup_run()
        with self.assertRaises(ValueError):
            m.save(self.root, 1, 1, 2, src)
        m.save(self.root, 1, 1, 1, src)
        m.save(self.root, 1, 1, 2, src)
        m.save(self.root, 1, 1, 2, src, replace=True)
        self.assertEqual(len(list(Path(info["output"]).glob("*.png"))), 2)
        self.assertEqual(len(list(Path(info["work"]).glob("round-2-source*.png"))), 2)
    def test_invalid_job_and_legacy(self):
        with self.assertRaises(ValueError):
            m.init_job(self.root, "../x")
        (self.root / "7").mkdir(parents=True)
        self.assertEqual(m.init_job(self.root, 7).name, "7")
    def test_install_and_no_overwrite(self):
        skills = Path(self.tmp.name) / "skills"
        target, job = installer.install(skills, self.root)
        self.assertTrue((target / "SKILL.md").exists())
        self.assertTrue((job / "参考").is_dir())
        with self.assertRaises(FileExistsError):
            installer.install(skills, self.root)
    def test_attachment_archive_deduplicates_and_records_chat(self):
        src = Path(self.tmp.name) / "产品.png"
        Image.new("RGB", (12, 12), "red").save(src)
        first = m.ingest(self.root, 1, [src], "制作洗护场景", ["会话图2：场景参考，无法导出"])
        second = m.ingest(self.root, 1, [src], "制作洗护场景", ["会话图2：场景参考，无法导出"])
        self.assertEqual(first, second)
        self.assertEqual(len(second["files"]), 1)
        self.assertEqual(len(second["messages"]), 1)
        self.assertEqual(len(list((m.job_path(self.root, 1) / "参考").glob("*.png"))), 1)
        self.assertTrue(src.exists())
    def test_upgrade_backs_up_and_keeps_project_root(self):
        skills = Path(self.tmp.name) / "skills"
        target, job = installer.install(skills, self.root)
        (target / "SKILL.md").write_text("旧版用户内容", encoding="utf-8")
        (job / "参考/保留.txt").write_text("不可丢失", encoding="utf-8")
        installer.install(skills, upgrade=True)
        backups = list((skills.parent / "skill-backups").glob("livestream-scene-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "SKILL.md").read_text(encoding="utf-8"), "旧版用户内容")
        self.assertEqual(json.loads((target / "project-settings.json").read_text(encoding="utf-8"))["project_root"], str(self.root.resolve()))
        self.assertEqual((job / "参考/保留.txt").read_text(encoding="utf-8"), "不可丢失")
        installed = load("installed_project", target / "scripts/project.py")
        self.assertEqual(installed.default_root(), self.root.resolve())
    def test_delivery_links_resolve_to_actual_run(self):
        info, src = self.setup_run()
        m.save(self.root, 1, 1, 1, src)
        m.save(self.root, 1, 1, 2, src)
        result = m.finish(self.root, 1, 1)
        for key, name in (("folder", None), ("image", "第二版.png"), ("record", "记录.md")):
            target = Path(result["output"]) / name if name else Path(result["output"])
            self.assertTrue(target.exists())
            self.assertIn(target.as_posix(), result["links"][key])
    def test_open_checks_location_and_uses_argument_list(self):
        with self.assertRaises(FileNotFoundError):
            m.open_output(self.root, 1, 1)
        info, _ = self.setup_run()
        with patch.object(m.sys, "platform", "linux"), patch.object(m.subprocess, "run") as launch:
            result = m.open_output(self.root, 1, 1)
            launch.assert_called_once_with(["xdg-open", info["output"]], check=True)
            self.assertEqual(result["opened"], info["output"])
if __name__ == "__main__":
    unittest.main()
