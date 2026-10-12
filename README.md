# Singbox Ruleset

[![Build RuleSet](https://github.com/huime180/singbox_ruleset/actions/workflows/singbox_ruleset.yml/badge.svg)](https://github.com/huime180/singbox_ruleset/actions/workflows/singbox_ruleset.yml)

Sing-Box 规则集，每日自动同步上游 [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script)
的 Clash 规则集并编译为 sing-box 的 `rule-set`。

本仓库是 [senshinya/singbox_ruleset](https://github.com/senshinya/singbox_ruleset) 的 fork，
在保留原有扁平分类的基础上，**恢复了上游的子目录层级**（例如 `Game/GameDownloadCN/GameDownloadCN.srs`）。

## 目录结构

```
rule/
├── Game/
│   ├── Game.json                  # 中间产物，供编译使用
│   ├── Game.srs                   # 顶层分类规则
│   ├── README.md                  # 规则统计与链接
│   ├── GameDownloadCN/
│   │   ├── GameDownloadCN.json
│   │   ├── GameDownloadCN.srs
│   │   └── README.md
│   ├── GameDownload/
│   └── Roblox/ ...
└── ...
```

每个分类目录下都会生成 `README.md`，包含规则类型统计、上游最后更新时间、
本仓库的 Github / CDN 链接，以及子规则列表。

## 使用方式

```json
{
  "route": {
    "rule_set": [
      {
        "type": "remote",
        "tag": "game-download-cn",
        "format": "binary",
        "url": "https://raw.githubusercontent.com/huime180/singbox_ruleset/main/rule/Game/GameDownloadCN/GameDownloadCN.srs",
        "download_detour": "direct"
      }
    ],
    "rules": [
      {
        "rule_set": ["game-download-cn"],
        "outbound": "direct"
      }
    ]
  }
}
```

CDN 加速可将域名替换为 `https://cdn.jsdelivr.net/gh/huime180/singbox_ruleset@main/...`。

## 自动构建

通过 GitHub Actions 每天 20:00 UTC（北京时间次日 04:00）自动运行，也可在
[Actions](https://github.com/huime180/singbox_ruleset/actions/workflows/singbox_ruleset.yml)
页面手动触发（`workflow_dispatch`）。构建流程：

1. 下载上游 Clash 规则；
2. `main.py` 递归转换为 sing-box 的 JSON 规则；
3. `compile.sh` 调用 `sing-box rule-set compile` 编译为 `.srs`；
4. 由 `github-actions[bot]` 提交并推送 `rule/`（源码与提交历史一并保留在 `main`）。

> 构建产生的中间文件（`venv/`、`asn/`、`ios_rule_script/` 等）已由 `.gitignore` 排除，不会入库。

### 可选 Secret

| Secret | 说明 |
| ---- | ---- |
| `MAXMIND_KEY` | [MaxMind](https://www.maxmind.com/en/geolite2/signup) 的 GeoLite2 license key，用于展开 `IP-ASN` 规则（如 Telegram、ChinaMax 等）。**未配置时脚本仍可正常运行**，仅跳过 `IP-ASN` 规则，其余规则不受影响。 |

配置入口：`Settings → Secrets and variables → Actions → New repository secret`。

## 本地调试

```bash
python3 main.py          # 生成 rule/ 下的 json 与 README
bash compile.sh          # 需要已安装 sing-box
```

如需反复调试，可先把上游仓库下载成本地 zip，再用 `SOURCE_REPO_ZIP` 指定，避免每次重复下载：

```bash
export SOURCE_REPO_ZIP=/path/to/ios_rule_script-master.zip
python3 main.py
```
