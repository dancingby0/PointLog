"""历史打卡记录迁移：把旧记录统一改为"不选时间"（兼容 v2.4 时段机制）。

背景：v2.4 起打卡时间从"单个时刻"改为**可选时段**（从 xx 起到 xx 结束），默认为不填。
旧记录里的 `ts` 只是记录时刻（多为提交时的默认值，并非真实时段），为让所有历史记录
呈现为"未选时间"，同时**不改变归属日与点数统计**，迁移规则：

- 归属日不变：`day = 按凌晨 4 点规则由旧 ts 推导`；
- 把 `ts` 规范化为该归属日的 `12:00`（本地时区，符合"补录某天"的语义）；
- `start_ts` / `end_ts` 置为 `null`（＝不选时间，不记时长）。

幂等：已是规范形式（ts 恰为该归属日 12:00 且两端为 null）的记录会被跳过，可反复执行。

用法：
    python migrate_entries.py              # 执行迁移
    python migrate_entries.py --dry-run    # 只看会改动多少条，不写盘
"""

import argparse
import datetime as dt
import json
import os
import shutil
from pathlib import Path

import data
from utils import date_of, parse_ts


def normalized_ts(ts) -> str | None:
    """旧 ts → 归属日 12:00（本地时区 ISO）；不可解析返回 None。"""
    try:
        day = date_of(parse_ts(ts))
    except (ValueError, TypeError):
        return None
    return dt.datetime.combine(day, dt.time(12, 0)).astimezone().isoformat()


def _needs_migration(entry: dict, norm: str) -> bool:
    """该记录是否需要改写（ts 非规范形式 / 缺时段字段 / 时段非空）。"""
    if entry.get("ts") != norm:
        return True
    if "start_ts" not in entry or "end_ts" not in entry:
        return True
    return entry.get("start_ts") is not None or entry.get("end_ts") is not None


def _write_json_atomic(path: Path, payload: dict) -> None:
    """原子写 data.json（先 .tmp 再替换）。"""
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def migrate_profile_file(path: Path, dry_run: bool = False) -> dict:
    """迁移单个档案的 data.json；返回 {path, entries, changed, skipped}。"""
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"path": str(path), "entries": 0, "changed": 0, "skipped": 0, "error": "读取失败"}

    entries = raw.get("entries") or []
    changed = 0
    skipped = 0
    for e in entries:
        norm = normalized_ts(e.get("ts"))
        if norm is None:
            skipped += 1                      # 时间不可解析：保持原样，交由人工确认
            continue
        if not _needs_migration(e, norm):
            continue
        changed += 1
        if not dry_run:
            e["ts"] = norm
            e["start_ts"] = None              # ＝不选时间
            e["end_ts"] = None

    if changed and not dry_run:
        # 首次改写前留一份原文件备份（data.json.bak），便于回退
        backup = path.with_suffix(".json.bak")
        if not backup.exists():
            try:
                shutil.copyfile(path, backup)
            except OSError:
                pass
        _write_json_atomic(path, raw)
    return {"path": str(path), "entries": len(entries), "changed": changed, "skipped": skipped}


def profile_data_files(root: Path | None = None) -> list[Path]:
    """枚举所有档案的 data.json（含账号层 data/<账号>/<档案>/data.json）。"""
    base = Path(root) if root is not None else data.DATA_DIR
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("data.json") if p.is_file())


def migrate_all(root: Path | None = None, dry_run: bool = False) -> dict:
    """迁移全部档案；返回汇总 {files, entries, changed, skipped, details}。"""
    files = profile_data_files(root)
    details = [migrate_profile_file(p, dry_run=dry_run) for p in files]
    return {
        "files": len(files),
        "entries": sum(d["entries"] for d in details),
        "changed": sum(d["changed"] for d in details),
        "skipped": sum(d["skipped"] for d in details),
        "details": details,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="把历史打卡记录统一改为\"不选时间\"（兼容 v2.4 时段机制，幂等）"
    )
    parser.add_argument("--dry-run", action="store_true", help="只统计不写盘")
    parser.add_argument("--data-dir", help="数据根目录（默认项目的 data/）")
    args = parser.parse_args(argv)

    root = Path(args.data_dir) if args.data_dir else None
    summary = migrate_all(root, dry_run=args.dry_run)
    if summary["files"] == 0:
        print("没有找到任何档案的 data.json（data/ 下暂无档案）")
        return 0

    prefix = "[dry-run] " if args.dry_run else ""
    for d in summary["details"]:
        note = f"  ({d['error']})" if d.get("error") else ""
        print(f"{prefix}{d['path']}: {d['changed']}/{d['entries']} 条 → 不选时间{note}")
    print(f"{'（未写盘）' if args.dry_run else ''}完成：档案 {summary['files']} 个，"
          f"记录 {summary['entries']} 条，改动 {summary['changed']} 条，"
          f"跳过（时间不可解析）{summary['skipped']} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
