#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""飞书 Base → RT 测试计划 → 聚合看板 的一体化 CLI。

子命令:
  login                      浏览器登录 RT，保存 token
  pull   --link URL [...]    拉飞书 Base、按状态/日期过滤，导出任务清单
  plans  --tasks FILE [...]  逐个 RT Task 拉测试计划，按产品线+关联计划过滤
  aggregate --plans FILE ... 按计划清单创建聚合看板并输出规模
  run    --link URL [...]    以上三步一条龙
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import feishu
import rt_api

HERE = Path(__file__).resolve().parent
DEFAULT_EXCLUDE = "未调度,已终止"


def _rt_task_id(url: str) -> str | None:
    m = re.search(r"RtTask/detail/(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"(\d{15,})", url)
    return m.group(1) if m else None


def cmd_pull(args) -> list[dict]:
    app, table, view = feishu.parse_link(args.link)
    rows = feishu.to_rows(app, table, view)
    print(f"表格记录 {len(rows)} 条", file=sys.stderr)

    exclude = {s.strip() for s in args.exclude_status.split(",") if s.strip()}
    picked = []
    for r in rows:
        status = (r.get("执行情况") or "").strip()
        if status in exclude:
            continue
        date = (r.get("日期") or "")[:10]
        if args.date_from and date < args.date_from:
            continue
        if args.date_to and date > args.date_to:
            continue
        rt = (r.get("_links") or {}).get("RT链接") or []
        tid = _rt_task_id(rt[0]) if rt else None
        if not tid:
            continue
        picked.append({
            "record_id": r["record_id"], "date": date, "status": status,
            "version": r.get("版本", ""), "taocan": r.get("套餐", ""),
            "rt_task_id": tid,
            "rt_url": rt[0],
            "board_links": (r.get("_links") or {}).get("看板链接") or [],
        })
    print(f"过滤后任务 {len(picked)} 条（排除 {sorted(exclude)}）", file=sys.stderr)
    print("状态分布:", dict(Counter(p["status"] for p in picked)), file=sys.stderr)
    return picked


def cmd_plans(args, tasks: list[dict]) -> list[dict]:
    out = []
    for i, t in enumerate(tasks, 1):
        try:
            plans = rt_api.test_plans(t["rt_task_id"])
        except SystemExit:
            raise
        except Exception as e:
            print(f"  [{i}/{len(tasks)}] {t['rt_task_id']} 拉取失败: {e}", file=sys.stderr)
            plans = []
        if args.product:
            plans = [p for p in plans if (p.get("product") or "") == args.product and p.get("link")]
        t2 = dict(t)
        t2["plans"] = [{
            "id": p.get("id"), "name": p.get("name"), "product": p.get("product"),
            "link": p.get("link"), "rt_board_id": p.get("rt_board_id"),
            "is_father_plan": p.get("is_father_plan"),
        } for p in plans]
        out.append(t2)
        print(f"  [{i}/{len(tasks)}] {t['rt_task_id']} 计划 {len(t2['plans'])}", file=sys.stderr)
    return out


def _collect_urls(tasks: list[dict]) -> list[str]:
    urls, seen = [], set()
    for t in tasks:
        for p in t.get("plans", []):
            u = p.get("link")
            if u and u not in seen:
                seen.add(u)
                urls.append(u)
    return urls


def cmd_aggregate(args, tasks: list[dict]) -> dict:
    urls = _collect_urls(tasks)
    if not urls:
        sys.exit("没有可聚合的测试计划（检查 --product 过滤条件）")
    print(f"待聚合计划 {len(urls)} 个", file=sys.stderr)
    if args.dry_run:
        for i, u in enumerate(urls, 1):
            print(f"  {i:>3}. {u}", file=sys.stderr)
        return {"dry_run": True, "plans": len(urls)}

    data = rt_api.create_multi_board(args.name, args.product, urls)
    bid = data.get("id")
    raw = rt_api.get_multi_board(bid)
    stats = rt_api.board_stats(raw)
    return {
        "url": rt_api.board_url(bid), "id": bid,
        "name": stats["name"] or args.name, "product": stats["product"] or args.product,
        "plans": stats["plans"], "cases": stats["cases"], "miles": stats["miles"],
        "submitted": len(urls),
    }


def _print_report(res: dict) -> None:
    if res.get("dry_run"):
        print(f"\n--dry-run：将聚合 {res['plans']} 个计划，未创建看板\n")
        return
    print("\n大看板已生成：")
    print(f"{res['url']}")
    print(f"看板名：{res['name']}")
    print(f"产品线：{res['product']}")
    print(f"规模：{res['plans']} 个测试计划（组合子看板）、{res['cases']} 条 case、总里程 {res['miles']} km")
    if res.get("submitted") and res["submitted"] != res["plans"]:
        print(f"（提交 {res['submitted']} 个，看板内合并后 {res['plans']} 个）")


def cmd_run(args) -> None:
    tasks = cmd_pull(args)
    if not tasks:
        sys.exit("过滤后没有任务，检查日期范围/状态条件")
    tasks = cmd_plans(args, tasks)
    res = cmd_aggregate(args, tasks)
    if args.out:
        Path(args.out).write_text(json.dumps({"tasks": tasks, "board": res}, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    _print_report(res)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="飞书 Base → RT 测试计划 → 聚合看板")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="浏览器登录 RT 并保存 token")

    def common_date(sp):
        sp.add_argument("--from", dest="date_from", default="", help="起始日期 YYYY-MM-DD")
        sp.add_argument("--to", dest="date_to", default="", help="结束日期 YYYY-MM-DD")

    pl = sub.add_parser("pull", help="拉飞书 Base 并按状态/日期过滤")
    pl.add_argument("--link", required=True, help="飞书 Base 链接（含 ?table=&view=）")
    pl.add_argument("--exclude-status", default=DEFAULT_EXCLUDE)
    pl.add_argument("--out", default="tasks.json")
    common_date(pl)

    pp = sub.add_parser("plans", help="拉每个任务的测试计划")
    pp.add_argument("--tasks", default="tasks.json")
    pp.add_argument("--product", default="HNP")
    pp.add_argument("--out", default="plans.json")

    pa = sub.add_parser("aggregate", help="按计划清单创建聚合看板")
    pa.add_argument("--plans", default="plans.json")
    pa.add_argument("--name", required=True)
    pa.add_argument("--product", default="HNP")
    pa.add_argument("--dry-run", action="store_true")

    pr = sub.add_parser("run", help="pull + plans + aggregate 一条龙")
    pr.add_argument("--link", required=True)
    pr.add_argument("--from", dest="date_from", default="")
    pr.add_argument("--to", dest="date_to", default="")
    pr.add_argument("--name", required=True)
    pr.add_argument("--product", default="HNP")
    pr.add_argument("--exclude-status", default=DEFAULT_EXCLUDE)
    pr.add_argument("--dry-run", action="store_true")
    pr.add_argument("--out", default="")
    return p


def main() -> None:
    args = build_parser().parse_args()

    if args.cmd == "login":
        import login
        login.run()
        return

    if args.cmd == "pull":
        tasks = cmd_pull(args)
        Path(args.out).write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已保存 {args.out}（{len(tasks)} 条）")
        return

    if args.cmd == "plans":
        tasks = json.loads(Path(args.tasks).read_text(encoding="utf-8"))
        out = cmd_plans(args, tasks)
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        urls = _collect_urls(out)
        print(f"已保存 {args.out}；符合条件计划 {len(urls)} 个")
        return

    if args.cmd == "aggregate":
        tasks = json.loads(Path(args.plans).read_text(encoding="utf-8"))
        _print_report(cmd_aggregate(args, tasks))
        return

    if args.cmd == "run":
        cmd_run(args)


if __name__ == "__main__":
    main()
