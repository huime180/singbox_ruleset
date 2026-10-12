#!/bin/bash
set -Eeuo pipefail

# 设置基础目录
base_dir="rule"

# 递归遍历 rule 下的所有层级：
# 顶层分类         rule/Game/Game.json              -> rule/Game/Game.srs
# 子分类（含子目录）rule/Game/GameDownloadCN/...json -> rule/Game/GameDownloadCN/GameDownloadCN.srs
cache_file=$(mktemp)
find "$base_dir" -type f -name '*.json' | sort > "$cache_file"

count=0
while IFS= read -r json_file; do
    # 以 JSON 所在目录名作为规则名
    folder_name=$(basename "$(dirname "$json_file")")
    json_name=$(basename "$json_file" .json)

    # 只编译 <目录名>.json，跳过其它无关 json
    if [[ "$json_name" != "$folder_name" ]]; then
        echo "Skip (name mismatch): $json_file"
        continue
    fi

    # 构建输出文件名 (与 JSON 相同，用 .srs 结尾)
    output_file="$(dirname "$json_file")/$folder_name.srs"

    # 执行 sing-box 命令
    sing-box rule-set compile --output "$output_file" "$json_file"

    echo "Processed: $json_file -> $output_file"
    count=$((count + 1))
done < "$cache_file"

rm -f "$cache_file"
echo "Total compiled: $count"
