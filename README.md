# rt-base-board

Claude Code 插件：把**飞书多维表格（Base）**里的路测任务一键聚合成 **RT 组合大看板**。

## 安装

```
/plugin marketplace add <owner>/rt-base-board
/plugin install rt-base-board@rt-base-board
```

装好后在 Claude Code 里直接说「按 10/19–10/25 聚合 HNP 看板」即可。

## 首次配置

| 凭据 | 做法 |
|---|---|
| 飞书 cookie | 浏览器打开目标 Base → F12 → Network → 任意请求 → Copy as cURL，取 `cookie` 串存到 `~/.claude/feishu/cookie.txt` |
| RT token | `python3 ~/.claude/plugins/.../skills/rt-base-board/main.py login`（弹浏览器登录一次） |

详细说明见 [skills/rt-base-board/README.md](skills/rt-base-board/README.md)。

## 命令

```bash
cd skills/rt-base-board
python3 main.py run --link "<飞书Base链接>" --from 2026-10-19 --to 2026-10-25 \
  --name "HNP-全量看板聚合-1019_1025" --product HNP
```

输出：

```
大看板已生成：
https://rt.momenta.works/micro_app_tbd/RtFibBoard/detail/<id>
看板名：<name>
产品线：HNP
规模：N 个测试计划（组合子看板）、M 条 case、总里程 K km
```

## 目录

```
.claude-plugin/
├── plugin.json          # 插件清单
└── marketplace.json     # marketplace 目录
skills/rt-base-board/    # 技能本体
```

## License

MIT
