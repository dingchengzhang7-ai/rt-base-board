---
name: rt-base-board
description: 从飞书多维表格（Base）链接一键生成 RT 聚合看板。按「日期范围 + 执行情况」过滤路测任务，逐条进 RT Task 拉测试计划，按产品线（HNP/UNP…）且「有关联路测计划」筛选，聚合成一张组合大看板并输出规模（计划数/case 数/总里程）。当用户说"把这个飞书表/Base 链接的任务聚合成看板""按日期聚合 HNP 看板""主线提测版本汇总看板""读表格→进 RT Task→找测试计划→合成大看板"时触发。
---

# rt-base-board

飞书 Base → RT 测试计划 → 聚合看板。

## 前置

| 依赖 | 获取方式 |
|---|---|
| 飞书 cookie | 浏览器打开 Base → F12 → Network → 任意请求 → Copy as cURL，取 `cookie` 串存到 `~/.claude/feishu/cookie.txt`（或设 `FEISHU_COOKIE` / `FEISHU_COOKIE_FILE`） |
| RT token | `python3 main.py login` 弹浏览器登录一次，token 存进 `config.json`（也可用环境变量 `EP_TOKEN`，或复用 `rt-spa-board` 的配置） |

cookie / token 过期表现：飞书 `code != 0` 或 RT 返回 401 → 重新取一次即可。

## 用法

```bash
cd ~/.claude/skills/rt-base-board

# 一条龙：飞书链接 + 日期范围 → 直接出看板
python3 main.py run \
  --link "https://momenta.feishu.cn/base/<app>?table=tblXXX&view=vewXXX" \
  --from 2026-10-19 --to 2026-10-25 \
  --name "HNP-全量看板聚合-1019_1025" \
  --product HNP

# 先干跑，只列计划不建板
python3 main.py run --link "<链接>" --from ... --to ... --name "<名>" --dry-run

# 分步
python3 main.py pull   --link "<链接>" --from 2026-10-19 --to 2026-10-25 --out tasks.json
python3 main.py plans  --tasks tasks.json --product HNP --out plans.json
python3 main.py aggregate --plans plans.json --name "<看板名>" --product HNP
```

输出格式：

```
大看板已生成：
https://rt.momenta.works/micro_app_tbd/RtFibBoard/detail/<id>
看板名：<name>
产品线：HNP
规模：N 个测试计划（组合子看板）、M 条 case、总里程 K km
```

## 规则（默认值，可用参数覆盖）

- **排除状态**：`执行情况 ∈ {未调度, 已终止}` → `--exclude-status`
- **日期口径**：Base 的「日期」字段，`--from`/`--to` 闭区间
- **计划筛选**：`product == --product` **且** `link`（关联路测计划）非空，按 link 去重
- **重名看板**：RT 后端同名直接返回已有看板（不会新建）；要新板就换名字

## 实现要点

- 飞书接口 `/space/api/v1/bitable/{app}/records`，`data.records` 是 **base64(gzip(JSON))**（`feishu.py`）
- RT 测试计划接口 `/backend/tbd/console/api/dlp/rt-manager/{task_id}/dlp_test_plan`（`rt_api.py`）
- 看板创建 `POST /backend/tbd/console/api/new/rt/board/multi/create`，body `{name, product, test_plan_url_list}`
- 规模统计取 `GET /board/multi/{id}` 的 `board_list`：计划数=长度，case=各 `case_list` 之和，里程=`sum_miles` 之和

## 读看板 / 对比页的规矩（重要）

- **按列名判断，不看左右**：对比视图里 BASE（旧版，只用于打 diff）可能排在左边，也可能在右边。
  只读「列名 = 目标版本」的那一列；列名带 `BASE` 标记、或版本号是旧版本（用于对比）的，一律跳过。
- **同名版本常按套餐合并**：Daily Board 的版本列会把该版本下多个套餐合并计算
  （例：`1027.08` 的 227 km + 199 km = 426 km）。SPA 里看到的可能是单套餐 / `路线:交集` 口径，
  数字对不上时先确认口径再报，别直接说"读错了"。
- **Daily Board 定位方式**：`main.py daily list --date <日期> --product HNP` 找到 board id →
  `daily get --id` 看版本池 → `daily report --id` 出对比报告，再按列名取目标版本。

## 坑

- **时间戳必须按本地时区换算**：飞书日期字段是 epoch 毫秒，用 `datetime(1970,1,1)+timedelta(ms)` 会少 8 小时，
  00:00–08:00 的记录会被归到前一天（曾导致 10/27 分组少一条）。统一用 `datetime.fromtimestamp(ms/1000)`。

- SSO 是 session cookie，关浏览器即失效，RT token 过期就重跑 `login`
- 刚创建的板里个别计划 `case_list` 为空属正常（数据还没回流）
- 图表/看板打开若缺 case，等回流后刷新即可，不必重建
