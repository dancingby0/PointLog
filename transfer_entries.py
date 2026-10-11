"""档案间打卡记录转移：把某个档案的 entries 合并到另一个档案（默认转移，可只复制）。

背景：打卡记录只属于单个档案（data/<账号>/<档案>/data.json 的 entries 块）。
把两个档案的历史合并（或把旧档案整体搬到新档案）时，手工改 JSON 容易重复、漏字段。

本工具保证：

- **幂等**：按 id 去重，目标里已有的记录直接跳过 → 反复执行不会翻倍；
- **先备份**：写盘前把源 / 目标各自的 data.json 各备份一份到同目录
  `data.json.bak-transfer-<时间戳>`（保留历史，不覆盖旧备份）；
- **原子写**：先写 .tmp 再替换（与 data.py 同策略），避免断电留下半截文件；
- **只搬打卡记录**：每日感想 daily_notes / 备忘 memos / 主目标 main_goal 一概不动，
  免得覆盖目标档案的私人内容；顺带把源的类别池 diary_tags 并入目标（`--no-merge-tags` 可关），
  让搬过来的类别在表单里仍能一键点选。

用法（建议先停掉正在运行的服务，避免写入竞态）：

    python transfer_entries.py --from e1tTil --to dancingby --account Felicia --dry-run
    python transfer_entries.py --from e1tTil --to dancingby --account Felicia
    python transfer_entries.py --from e1tTil --to dancingby --account Felicia --copy
"""

import argparse
import copy
import datetime as dt
import json
import os
import shutil
from pathlib import Path

import data


def profile_data_path(profile: str, account: str = "", root: Path | None = None) -> Path:
    """档案 data.json 路径：有账号 → <root>/<账号>/<档案>/data.json；无账号 → <root>/<档案>/。"""
    data.validate_profile_name(profile)
    base = Path(root) if root is not None else data.DATA_DIR
    return (base / account / profile if account else base / profile) / "data.json"


def _sum_points(entries: list) -> int:
    """记录点数合计（容错：点数缺失 / 非数字按 0 计）。"""
    total = 0
    for e in entries:
        try:
            total += int(e.get("points") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _load_raw(path: Path) -> dict:
    """读 data.json 并补齐缺失字段（缺字段补默认，不写盘）；不存在 / 损坏抛 ValueError。"""
    if not path.exists():
        raise ValueError(f"文件不存在: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"读取失败（{exc}）: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"结构异常（顶层不是对象）: {path}")
    base = data.default_data()
    for key in base:
        raw.setdefault(key, copy.deepcopy(base[key]))
    if not isinstance(raw["entries"], list):
        raw["entries"] = []
    return raw


def _entry_key(entry: dict):
    """疑似重复判定键：内容 + 点数 + ts 的日期部分（只看年月日，时间可被补录改写）。"""
    return (str(entry.get("content") or "").strip(), entry.get("points"),
            str(entry.get("ts") or "")[:10])


def _write_json_atomic(path: Path, payload: dict) -> None:
    """原子写 data.json（先 .tmp 再替换）。"""
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def _backup(path: Path, stamp: str) -> Path | None:
    """把 data.json 备份为 data.json.bak-transfer-<stamp>（已存在则加 -2/-3… 序号，绝不覆盖）。"""
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.bak-transfer-{stamp}")
    i = 2
    while backup.exists():          # 同一秒内重复执行也不覆盖历史备份
        backup = path.with_name(f"{path.name}.bak-transfer-{stamp}-{i}")
        i += 1
    shutil.copyfile(path, backup)
    return backup


def transfer(from_profile: str, to_profile: str, account: str = "",
             copy_only: bool = False, merge_tags: bool = True,
             dry_run: bool = False, root: Path | None = None,
             stamp: str | None = None) -> dict:
    """把 from 档案的打卡记录并入 to 档案；返回汇总 dict（含 moved/backups/written）。"""
    if from_profile == to_profile:
        raise ValueError("源档案与目标档案不能相同")
    src_path = profile_data_path(from_profile, account, root)
    dst_path = profile_data_path(to_profile, account, root)
    src = _load_raw(src_path)
    dst = _load_raw(dst_path)

    seen = {str(e.get("id")) for e in dst["entries"]}
    moved: list[dict] = []
    skipped = 0                      # 目标已有同 id（＝之前搬过）：跳过，保证幂等
    for e in src["entries"]:
        key = str(e.get("id"))
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        moved.append(e)

    # 疑似重复：内容 + 点数 + 日期都相同（不自动删，只提示人工确认）
    dst_keys = {_entry_key(e) for e in dst["entries"]}
    hints = [e for e in moved if _entry_key(e) in dst_keys]

    tags_added: list[str] = []
    if merge_tags:
        existing = list(dst.get("diary_tags") or [])
        for tag in src.get("diary_tags") or []:
            if tag not in existing:
                existing.append(tag)
                tags_added.append(tag)
        dst["diary_tags"] = existing

    info = {
        "source": str(src_path), "target": str(dst_path),
        "source_entries": len(src["entries"]), "source_points": _sum_points(src["entries"]),
        "target_before": len(dst["entries"]), "target_points_before": _sum_points(dst["entries"]),
        "moved": len(moved), "moved_points": _sum_points(moved),
        "skipped_existing": skipped, "duplicate_hints": hints,
        "tags_added": tags_added, "copy_only": copy_only,
        "target_after": len(dst["entries"]) + len(moved),
        "written": False, "backups": [],
    }
    if dry_run or (not moved and not tags_added):
        return info                  # dry-run 或无事可做：不备份、不写盘

    stamp = stamp or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    info["backups"] = [str(p) for p in
                       filter(None, (_backup(src_path, stamp), _backup(dst_path, stamp)))]

    dst["entries"] = dst["entries"] + copy.deepcopy(moved)
    _write_json_atomic(dst_path, dst)
    if not copy_only:
        src["entries"] = []
        _write_json_atomic(src_path, src)      # 转移：源档案只清空打卡记录，其余内容保留

    info["written"] = True
    info["target_after"] = len(dst["entries"])
    return info


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="把某档案的打卡记录转移到另一个档案（幂等、先备份、只搬打卡记录）"
    )
    parser.add_argument("--from", dest="src", required=True, help="源档案名")
    parser.add_argument("--to", dest="dst", required=True, help="目标档案名")
    parser.add_argument("--account", default="", help="账号名（留空＝无账号旧布局 data/<档案>/）")
    parser.add_argument("--copy", action="store_true",
                        help="只复制，保留源档案记录（默认＝转移：源档案打卡记录清空）")
    parser.add_argument("--no-merge-tags", action="store_true", help="不把源的类别池并入目标")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写盘")
    parser.add_argument("--data-dir", help="数据根目录（默认项目的 data/）")
    args = parser.parse_args(argv)

    root = Path(args.data_dir) if args.data_dir else None
    try:
        info = transfer(args.src, args.dst, account=args.account, copy_only=args.copy,
                        merge_tags=not args.no_merge_tags, dry_run=args.dry_run, root=root)
    except ValueError as exc:
        print(f"× {exc}")
        return 1

    prefix = "[dry-run] " if args.dry_run else ""
    print(f"{prefix}源档案 {args.src}: {info['source_entries']} 条 / {info['source_points']} 点")
    print(f"{prefix}目标档案 {args.dst}: {info['target_before']} 条 → {info['target_after']} 条"
          f"（{info['target_points_before']} 点 → "
          f"{info['target_points_before'] + info['moved_points']} 点）")
    print(f"{prefix}{'只复制' if info['copy_only'] else '转移（源档案打卡记录清空）'}："
          f"搬入 {info['moved']} 条 / {info['moved_points']} 点，"
          f"跳过（目标已有同 id）{info['skipped_existing']} 条")
    if info["tags_added"]:
        print(f"{prefix}类别池并入 {len(info['tags_added'])} 个：{'、'.join(info['tags_added'])}")
    if info["duplicate_hints"]:
        print(f"{prefix}⚠ 疑似重复 {len(info['duplicate_hints'])} 条"
              "（内容 + 点数 + 日期都相同，未自动处理，请人工确认）：")
        for e in info["duplicate_hints"]:
            print(f"    {str(e.get('ts'))[:10]}  {e.get('content')}  {e.get('points')} 点")
    if not info["written"]:
        print(f"{prefix}{'（未写盘）' if args.dry_run else '（无改动，未写盘）'}")
        return 0
    for b in info["backups"]:
        print(f"{prefix}备份: {b}")
    print(f"{prefix}完成：{info['source']} → {info['target']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

