#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""飞书 Base 客户端：解析链接、拉 schema 与全量记录、按字段类型还原可读值。

接口（实测 2026-10）：
  GET /space/api/v1/bitable/{app}/clientvars?tableID=&viewID=...
  GET /space/api/v1/bitable/{app}/records?tableId=&viewId=&offset=&limit=
两者返回的 data.records / data.table 都是 base64(gzip(JSON))，以 H4sI 开头。
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HOST = os.environ.get("FEISHU_HOST", "https://momenta.feishu.cn").rstrip("/")
DEFAULT_COOKIE = Path(os.environ.get("FEISHU_COOKIE_FILE") or Path.home() / ".claude" / "feishu" / "cookie.txt")

TEXT, NUMBER, SELECT, DATE, URL, ATTACH = 1, 2, 3, 5, 15, 17


def cookie() -> str:
    env = os.environ.get("FEISHU_COOKIE")
    if env:
        return env.strip()
    p = Path(os.environ.get("FEISHU_COOKIE_FILE") or DEFAULT_COOKIE)
    if not p.exists():
        sys.exit(f"缺少飞书 cookie：{p}\n用浏览器打开表格 → F12 → Network → 任意请求 → Copy as cURL，"
                 f"把 cookie 串存到该文件，或设环境变量 FEISHU_COOKIE")
    return p.read_text(encoding="utf-8").strip()


def parse_link(url: str) -> tuple[str, str, str]:
    """https://momenta.feishu.cn/base/{app}?table={tbl}&view={view}"""
    u = urllib.parse.urlparse(url.strip())
    parts = [p for p in u.path.split("/") if p]
    if "base" not in parts:
        sys.exit(f"无法识别的 Base 链接：{url}")
    app = parts[parts.index("base") + 1]
    q = urllib.parse.parse_qs(u.query)
    table = (q.get("table") or [""])[0]
    view = (q.get("view") or [""])[0]
    if not table:
        sys.exit("链接里缺少 table 参数（?table=tblXXXX）")
    return app, table, view


def _get(path: str, params: dict) -> dict:
    url = f"{HOST}/space/api/v1/bitable/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "cookie": cookie(),
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/156.0.0.0 Safari/537.36",
            "accept-encoding": "identity",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("code") != 0:
        sys.exit(f"飞书接口报错（cookie 可能过期）：{payload.get('code')} {payload.get('msg')}")
    return payload["data"]


def _ungzip(value):
    if isinstance(value, str) and value.startswith("H4sI"):
        return json.loads(gzip.decompress(base64.b64decode(value)).decode("utf-8"))
    return value


def fetch_schema(app: str, table: str, view: str) -> dict:
    data = _get(f"{app}/clientvars", {
        "tableID": table, "viewID": view, "record": "", "recordLimit": 1,
        "ondemandLimit": 1, "needBase": "true", "viewLazyLoad": "true",
        "ondemandVer": 2, "openType": 0, "noMissCS": "true",
        "optimizationFlag": 1, "removeFmlExtra": "true",
    })
    return _ungzip(data["table"])["fieldMap"]


def _fetch_page(app: str, table: str, view: str, offset: int, limit: int) -> dict:
    data = _get(f"{app}/records", {
        "tableId": table, "viewId": view, "viewLazyLoad": "true",
        "offset": offset, "limit": limit, "tableID": table, "viewID": view,
        "removeFmlExtra": "true",
    })
    return _ungzip(data["records"])


def fetch_records(app: str, table: str, view: str, page: int = 3000) -> dict:
    """服务端单次上限 3000 条，超出自动翻页合并。"""
    first = _fetch_page(app, table, view, 0, page)
    total = first.get("tableRecordNum") or 0
    merged = first
    while len(merged.get("recordMap") or {}) < total:
        offset = len(merged["recordMap"])
        nxt = _fetch_page(app, table, view, offset, page)
        added = 0
        for rid, rec in (nxt.get("recordMap") or {}).items():
            if rid not in merged["recordMap"]:
                merged["recordMap"][rid] = rec
                added += 1
        for k, v in ((nxt.get("resourceMap") or {}).get("attachments") or {}).get("data", {}).items():
            merged.setdefault("resourceMap", {}).setdefault("attachments", {}).setdefault("data", {})[k] = v
        if not added:
            break
    return merged


def _ms_to_str(ms) -> str:
    if not isinstance(ms, (int, float)):
        return ""
    # 飞书时间戳是 epoch 毫秒，必须按本地时区换算；直接 epoch 加法会少 8 小时，
    # 导致 00:00–08:00 的记录被归到前一天。
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def _render(field: dict, cell: dict) -> tuple[str, list[str]]:
    if not cell:
        return "", []
    val = cell.get("value")
    if val is None:
        return "", []
    ftype = field.get("type")
    links: list[str] = []

    if ftype == SELECT:
        names = {o["id"]: o["name"] for o in field.get("property", {}).get("options", [])}
        picked = val if isinstance(val, list) else [val]
        return ", ".join(names.get(v, str(v)) for v in picked), links
    if ftype == DATE:
        return _ms_to_str(val), links
    if ftype == NUMBER:
        return str(val), links
    if ftype == ATTACH:
        return f"{len(val)} 个附件", links

    if isinstance(val, list):
        parts = []
        for item in val:
            if isinstance(item, dict):
                if item.get("link"):
                    links.append(item["link"])
                parts.append(item.get("text") or item.get("name") or "")
            else:
                parts.append(str(item))
        return "".join(parts), links
    return str(val), links


def to_rows(app: str, table: str, view: str, order: list[str] | None = None) -> list[dict]:
    """返回 [{字段名: 文本, "_links": {字段名: [url]}, "record_id": ...}]。"""
    fields = fetch_schema(app, table, view)
    payload = fetch_records(app, table, view)
    record_map = payload["recordMap"]
    attachments = payload.get("resourceMap", {}).get("attachments", {}).get("data", {})

    by_name = {f["name"]: fid for fid, f in fields.items()}
    columns = [n for n in (order or []) if n in by_name] + [n for n in by_name if n not in (order or [])]

    rows = []
    for rid, rec in record_map.items():
        row = {"record_id": rid}
        links = {}
        for name in columns:
            fid = by_name[name]
            text, found = _render(fields[fid], rec.get(fid))
            att = attachments.get(fid, {}).get(rid, [])
            if att:
                text = "; ".join(a.get("name", "") for a in att)
            row[name] = text
            if found:
                links[name] = found
        row["_links"] = links
        rows.append(row)
    return rows
