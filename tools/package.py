"""Build a source release from an explicit public-file allowlist."""
import argparse
import hashlib
import re
import zipfile
from pathlib import Path

def build(version="1.2.1", destination=None):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("version must be MAJOR.MINOR.PATCH")
    root = Path(__file__).resolve().parents[1]
    destination = Path(destination or root / "dist").resolve()
    destination.mkdir(parents=True, exist_ok=True)
    result = destination / f"livestream-scene-skill-v{version}.zip"
    selected = [root / p for p in ("README.md", "LICENSE", "requirements.txt", "install.py", ".gitignore", "TESTING.md", "VALIDATION.md")]
    for directory in ("skills", "docs", "tests", ".github", "tools"):
        selected.extend((root / directory).rglob("*"))
    selected = sorted(set(p for p in selected if p.is_file() and not p.is_symlink()
                          and "__pycache__" not in p.parts and p.suffix != ".pyc"
                          and p.name != "project-settings.json"))
    with zipfile.ZipFile(result, "x", zipfile.ZIP_DEFLATED) as archive:
        for p in selected:
            archive.write(p, Path("livestream-scene-skill") / p.relative_to(root))
    with zipfile.ZipFile(result) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP verification failed")
    digest = hashlib.sha256(result.read_bytes()).hexdigest()
    checksum = destination / "SHA256SUMS.txt"
    checksum.write_text(f"{digest}  {result.name}\n", encoding="utf-8")
    print(f"{result}\n{checksum}\n{len(selected)} files")
    return result
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="1.2.1")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    build(args.version, args.output_dir)
