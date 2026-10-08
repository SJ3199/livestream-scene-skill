"""Minimal batch delivery: PNGs and matching Chinese TXT only."""
import argparse
import json
import re
from pathlib import Path
from PIL import Image, ImageOps
from project import default_root

def output(root, batch):
    if not batch or batch in {'.', '..'} or any(x in batch for x in '/\\:'):
        raise ValueError('批次名称必须为单个目录名')
    base = Path(root).resolve()
    parent = base / batch
    path = parent / '全部场景版本'
    if parent.is_symlink() or path.is_symlink():
        raise ValueError('不接受输出目录符号链接')
    path.mkdir(parents=True, exist_ok=True)
    return path

def stem(scene, version, scenes=9, versions=9):
    if not (1 <= scene <= scenes and 1 <= version <= versions):
        raise ValueError('编号超出声明范围；多位编号需预先统一字段宽度')
    return f'{scene:0{len(str(scenes))}d} ({version:0{len(str(versions))}d})'

def save(root, batch, scene, version, source, scenes=9, versions=9, width=1080, height=1920):
    if min(width, height) < 1:
        raise ValueError('尺寸必须为正')
    path = output(root, batch)
    target = path / (stem(scene, version, scenes, versions) + '.png')
    if target.exists() or target.with_suffix('.txt').exists():
        raise FileExistsError(target)
    if version > 1 and not (path / (stem(scene, version - 1, scenes, versions) + '.png')).exists():
        raise ValueError('先保存前一版本，不跳号')
    with Image.open(source) as raw:
        im = ImageOps.exif_transpose(raw)
        size = im.size
        if abs(size[0] / size[1] / (width / height) - 1) > .02:
            raise ValueError('比例偏差超过2%，不能强行拉伸')
        im.resize((width, height), Image.Resampling.LANCZOS).save(target)
    return {'image': str(target), 'source_size': list(size), 'output_size': [width, height],
            'normalization': 'Lanczos resize without crop'}

def check(root, batch, scenes=9, versions=9, expected_scenes=None):
    path = output(root, batch)
    entries = list(path.iterdir())
    if any(not p.is_file() or p.is_symlink() or p.suffix not in {'.png', '.txt'} for p in entries):
        raise ValueError('图片目录只能包含PNG与同名TXT')
    images = sorted(path.glob('*.png'))
    if not images:
        raise ValueError('没有图片')
    found = {}
    for p in images:
        match = re.fullmatch(r'(\d+) \((\d+)\)', p.stem)
        if not match:
            raise ValueError(f'命名错误：{p.name}')
        s, v = map(int, match.groups())
        if p.stem != stem(s, v, scenes, versions):
            raise ValueError(f'编号宽度不一致：{p.name}')
        found.setdefault(s, []).append(v)
        txt = p.with_suffix('.txt')
        if not txt.exists() or not txt.read_text(encoding='utf-8').strip():
            raise ValueError(f'缺少同名UTF-8中文提示词：{p.name}')
        with Image.open(p) as im:
            im.verify()
    if any(not p.with_suffix('.png').exists() for p in path.glob('*.txt')):
        raise ValueError('存在孤立TXT')
    if any(sorted(v) != list(range(1, max(v) + 1)) for v in found.values()):
        raise ValueError('版本编号不连续')
    if expected_scenes is not None and set(found) != set(range(1, expected_scenes + 1)):
        raise ValueError('场景数量不完整')
    return {'folder': str(path), 'images': [p.name for p in images],
            'link': f'[打开结果文件夹](<{path.as_posix()}>)'}

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['init', 'save', 'check'])
    p.add_argument('--root', default=str(default_root()))
    p.add_argument('--batch', required=True)
    p.add_argument('--scene', type=int)
    p.add_argument('--version', type=int)
    p.add_argument('--scenes', type=int, default=9)
    p.add_argument('--versions', type=int, default=9)
    p.add_argument('--expected-scenes', type=int)
    p.add_argument('--source')
    a = p.parse_args()
    if a.command == 'save':
        if a.scene is None or a.version is None or not a.source:
            p.error('save需要--scene、--version、--source')
        result = save(a.root, a.batch, a.scene, a.version, a.source, a.scenes, a.versions)
    elif a.command == 'check':
        result = check(a.root, a.batch, a.scenes, a.versions, a.expected_scenes)
    else:
        result = {'folder': str(output(a.root, a.batch))}
    print(json.dumps(result, ensure_ascii=False, indent=2))
