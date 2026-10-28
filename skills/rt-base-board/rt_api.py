#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RT 后端最小客户端：测试计划查询 + 组合看板创建/读取。

认证：Authorization: <EP token>（无 Bearer 前缀），token 来自
  1) 环境变量 EP_TOKEN
  2) 本 skill 的 config.json -> rt_token
  3) 兄弟 skill rt-spa-board/config.json -> auth.token
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

BASE = os.environ.get("RT_BASE_URL", "https://rt.momenta.works").rstrip("/")
PLAN_API = "/backend/tbd/console/api/dlp/rt-manager/{tid}/dlp_test_plan"
MULTI_CREATE = "/backend/tbd/console/api/new/rt/board/multi/create"
MULTI_GET = "/backend/tbd/console/api/new/rt/board/multi/{bid}"
SHARE_DETAIL = "/micro_app_tbd/RtFibBoard/detail"

CONFIG = Path(__file__).resolve().parent / "config.json"
SIBLING = Path.home() / ".claude" / "skills" / "rt-spa-board" / "config.json"


def load_config() -> dict:
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def save_config(data: dict) -> None:
    CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def token() -> str:
    t = os.environ.get("EP_TOKEN") or load_config().get("rt_token")
    if not t and SIBLING.exists():
        try:
            t = (json.loads(SIBLING.read_text(encoding="utf-8")).get("auth") or {}).get("token")
        except ValueError:
            t = None
    if not t:
        sys.exit("缺少 RT token：先运行 `python3 main.py login` 登录一次，或设环境变量 EP_TOKEN")
    return t


def _request(method: str, path: str, **kw) -> Any:
    resp = requests.request(method, BASE + path, headers={
        "Authorization": token(), "Content-Type": "application/json",
    }, timeout=60, **kw)
    if resp.status_code == 401:
        sys.exit("RT 认证失败：token 过期，运行 `python3 main.py login` 重新登录")
    body = resp.json()
    status = body.get("status", body.get("code"))
    if status not in (10000, 0):
        sys.exit(f"RT 接口错误 (status={status}): {body.get('message')}")
    return body.get("data")


def test_plans(task_id: str) -> list[dict]:
    """某 RT Task 下的全部测试计划。"""
    data = _request("GET", PLAN_API.format(tid=task_id))
    return data if isinstance(data, list) else []


def create_multi_board(name: str, product: str, plan_urls: list[str]) -> dict:
    return _request("POST", MULTI_CREATE, json={
        "name": name, "product": product, "test_plan_url_list": list(plan_urls),
    })


def get_multi_board(board_id: int | str) -> dict:
    return _request("GET", MULTI_GET.format(bid=board_id))


def board_url(board_id: int | str) -> str:
    return f"{BASE}{SHARE_DETAIL}/{board_id}"


def board_stats(raw: dict) -> dict:
    items = raw.get("board_list") or []
    cases = sum(len(b.get("case_list") or []) for b in items)
    miles = sum(float(b.get("sum_miles") or 0) for b in items)
    return {
        "name": raw.get("name"),
        "product": raw.get("product"),
        "plans": len(items),
        "cases": cases,
        "miles": round(miles),
    }
