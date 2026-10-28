#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打开浏览器登录 RT，抓取 localStorage 里的 ep_access_token 并保存。

SSO 会话是 session cookie，关浏览器即失效，所以每次 token 过期都需要重跑一次。
"""
from __future__ import annotations

import os
import sys

import rt_api

ENTRY = f"{rt_api.BASE}/micro_app_tbd/RtTask"
CHANNELS = [os.environ.get("RT_BROWSER_CHANNEL") or "msedge", "chrome"]


def run() -> str:
    token = _login()
    cfg = rt_api.load_config()
    cfg["rt_token"] = token
    rt_api.save_config(cfg)
    print(f"✅ RT token 已保存（{token[:8]}...{token[-4:]}）")
    return token


def _login() -> str:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        sys.exit("需要 Playwright：pip install playwright（登录复用本机已安装的 Edge/Chrome，无需 playwright install）")

    async def _go():
        async with async_playwright() as p:
            browser = None
            for ch in CHANNELS:
                try:
                    browser = await p.chromium.launch(channel=ch, headless=False)
                    break
                except Exception:
                    continue
            if browser is None:
                sys.exit("找不到可用的 Edge/Chrome，请安装其一或设 RT_BROWSER_CHANNEL")
            ctx = await browser.new_context(viewport={"width": 1500, "height": 950})
            page = await ctx.new_page()
            print(">>> 请在窗口里登录 RT，完成后自动继续 <<<", flush=True)
            try:
                await page.goto(ENTRY, wait_until="domcontentloaded", timeout=90000)
            except Exception:
                pass
            for i in range(300):
                try:
                    tok = await page.evaluate(
                        "() => { try { return localStorage.getItem('ep_access_token') } catch(e) { return null } }"
                    )
                except Exception:
                    tok = None
                if tok:
                    print(f"[OK] 已获取 token（{i*2}s）", flush=True)
                    await browser.close()
                    return tok
                if i % 15 == 0:
                    print(f"[{i*2}s] 等待登录：{page.url[:80]}", flush=True)
                await page.wait_for_timeout(2000)
            await browser.close()
            return None

    import asyncio
    tok = asyncio.run(_go())
    if not tok:
        sys.exit("登录超时，未获取到 token")
    return tok


if __name__ == "__main__":
    run()
