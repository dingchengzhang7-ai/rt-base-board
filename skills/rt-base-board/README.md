# rt-base-board

把**飞书多维表格（Base）**里的路测任务，一键聚合成一张 **RT 组合大看板**。

流程：飞书 Base 链接 → 按「日期 + 执行情况」过滤任务 → 逐个 RT Task 拉测试计划 →
筛出「产品线 + 有关联路测计划」的计划 → 调 RT 接口建组合看板 → 输出规模统计。

## 安装

### 方式一：作为 Claude Code skill（推荐）

```bash
# 解压后放到 skills 目录
mv rt-base-board ~/.claude/skills/
# 装依赖
pip install -r ~/.claude/skills/rt-base-board/requirements.txt
```

之后在 Claude Code 里直接说「按 10/19–10/25 聚合 HNP 看板」就会自动调用。

### 方式二：纯命令行

```bash
cd rt-base-board
pip install -r requirements.txt
python3 main.py --help
```

## 配置（两样凭据）

### 1. 飞书 cookie

浏览器打开目标 Base → `F12` → **Network** → 任选一个请求 → 右键 **Copy as cURL** →
取其中的 `cookie` 串，存成：

```
~/.claude/feishu/cookie.txt
```

或用环境变量 `FEISHU_COOKIE` / `FEISHU_COOKIE_FILE` 指向别处。

### 2. RT token（二选一）

```bash
# A. 自动：弹浏览器登录一次，自动抓 token 存进 config.json
python3 main.py login
# 需要 pip install playwright（复用本机已装 Edge/Chrome，无需 playwright install）

# B. 手动：从浏览器 localStorage 取 ep_access_token，写进 config.json
cp config.example.json config.json
# 编辑 config.json: {"rt_token": "<从 localStorage 复制的 ep_access_token>"}
```

也可用环境变量 `EP_TOKEN` 覆盖。

## 用法

```bash
# 一条龙
python3 main.py run \
  --link "https://<tenant>.feishu.cn/base/<app>?table=tblXXX&view=vewXXX" \
  --from 2026-10-19 --to 2026-10-25 \
  --name "HNP-全量看板聚合-1019_1025" \
  --product HNP

# 先看会聚合哪些计划，不建板
python3 main.py run --link "<链接>" --from ... --to ... --name "<名>" --dry-run

# 分步
python3 main.py pull      --link "<链接>" --from ... --to ... --out tasks.json
python3 main.py plans     --tasks tasks.json --product HNP --out plans.json
python3 main.py aggregate --plans plans.json --name "<看板名>" --product HNP
```

输出：

```
大看板已生成：
https://rt.momenta.works/micro_app_tbd/RtFibBoard/detail/<id>
看板名：<name>
产品线：HNP
规模：N 个测试计划（组合子看板）、M 条 case、总里程 K km
```

## 参数

| 参数 | 说明 |
|---|---|
| `--from` / `--to` | 按 Base「日期」字段过滤，闭区间 |
| `--exclude-status` | 默认 `未调度,已终止` |
| `--product` | 默认 `HNP`（`UNP`、`NP MAX` 等同理） |
| `--dry-run` | 只列计划，不创建看板 |

规则：计划需满足 `product == --product` **且** `link`（关联路测计划）非空，按 link 去重。

## 环境变量

| 变量 | 默认 |
|---|---|
| `FEISHU_HOST` | `https://momenta.feishu.cn` |
| `RT_BASE_URL` | `https://rt.momenta.works` |
| `EP_TOKEN` | 无（优先于 config.json） |
| `FEISHU_COOKIE_FILE` | `~/.claude/feishu/cookie.txt` |
| `RT_BROWSER_CHANNEL` | `msedge`（失败回落到 `chrome`） |

## 常见问题

**飞书报 `code != 0` / RT 报 401** —— 凭据过期。飞书重新取 cookie；RT 跑 `main.py login`。

**看板里个别计划 case 为 0** —— 数据还没回流，等回流后刷新即可，不用重建。

**同名看板没新建** —— RT 后端同名会直接返回已有看板，换个名字才会创建新板。

**返回的计划数比提交的少** —— 看板内按测试计划做了合并，属正常。

## 目录

```
main.py         CLI
feishu.py       飞书 Base 客户端（链接解析 / 自动翻页 / 字段还原）
rt_api.py       RT 客户端（测试计划 / 建板 / 看板统计）
login.py        浏览器登录抓 token
SKILL.md        Claude Code skill 说明
```
