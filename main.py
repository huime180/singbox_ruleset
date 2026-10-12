import csv
import os
import re
import shutil
import logging
import requests
import zipfile
import json
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}

current_dir = os.path.dirname(os.path.abspath(__file__))
asn_url = 'https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-ASN-CSV&license_key={}&suffix=zip'
asn_v4 = defaultdict(list)
asn_v6 = defaultdict(list)

asn_ready = False

def init():
    global asn_ready
    # 删除已有文件夹
    dir_path = os.path.join(current_dir, 'rule')
    if os.path.exists(dir_path) and os.path.isdir(dir_path):
        logging.warning('{} exists, delete!', dir_path)
        shutil.rmtree(dir_path)
    os.makedirs(dir_path)

    # 获取 asn 文件
    maxmind_key = (os.environ.get('MAXMIND_KEY') or '').strip()
    if not maxmind_key:
        # 无 key 时降级运行：IP-ASN 规则无法展开，其余规则照常生成
        logging.warning('MAXMIND_KEY not set, skip asn download; '
                        'IP-ASN rules will be skipped and asn lookups disabled')
        return
    logging.info('downloading asn file...')
    zip_path = os.path.join(current_dir, 'asn.zip')
    response = requests.get(asn_url.format(maxmind_key), headers=headers)
    if response.status_code == 200:
        with open(zip_path, 'wb') as file:
            file.write(response.content)
        logging.info('downloading asn file complete')
    else:
        logging.critical(f'downloading asn file error, error code {response.status_code}')
        exit(1)

    # 解压 asn 文件
    asn_folder_path = os.path.join(current_dir, 'asn')
    os.makedirs(asn_folder_path, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        file_list = zip_ref.namelist()
        # 检查 ZIP 文件中是否只有一个文件夹
        outer_folder = file_list[0].split('/')[0]
        for file_name in file_list:
            # 跳过第一层级的文件夹名
            if file_name.startswith(outer_folder + '/'):
                # 去掉第一层级的文件夹名
                file_name_without_outer = file_name[len(outer_folder) + 1:]
                # 设定解压的目标路径
                target_file_path = os.path.join(asn_folder_path, file_name_without_outer)
                # 解压文件到目标路径
                with open(target_file_path, 'wb') as output_file:
                    output_file.write(zip_ref.read(file_name))
        logging.info(f"unzip asn files to {asn_folder_path}")
    
    # 汇总 asn 信息
    asn_v4_file = os.path.join(asn_folder_path, 'GeoLite2-ASN-Blocks-IPv4.csv')
    asn_v6_file = os.path.join(asn_folder_path, 'GeoLite2-ASN-Blocks-IPv6.csv')
    with open(asn_v4_file, mode='r', encoding='utf-8') as f:
        csv_reader = csv.reader(f, delimiter=',')
        next(csv_reader)
        for row in csv_reader:
            if not row or len(row) < 2:
                continue
            asn_v4[int(row[1])].append(row[0])
    with open(asn_v6_file, mode='r', encoding='utf-8') as f:
        csv_reader = csv.reader(f, delimiter=',')
        next(csv_reader)
        for row in csv_reader:
            if not row or len(row) < 2:
                continue
            # 上游此处误写入 asn_v4，导致 IPv6 地址段被并入 IPv4 结果，这里修正为 asn_v6
            asn_v6[int(row[1])].append(row[0])
    logging.info('aggregating asn info finishes')
    asn_ready = True

source_repo_url = "https://github.com/blackmatrix7/ios_rule_script/archive/refs/heads/master.zip"
def download_source_repo():
    source_zip = os.path.join(current_dir, 'ios_rule_script.zip')
    # 本地调试时可用 SOURCE_REPO_ZIP 指向已下载的上游 zip，避免重复下载
    local_zip = (os.environ.get('SOURCE_REPO_ZIP') or '').strip()
    if local_zip:
        if not os.path.exists(local_zip):
            logging.critical('SOURCE_REPO_ZIP not found: %s', local_zip)
            exit(1)
        logging.info('using local source zip %s', local_zip)
        shutil.copyfile(local_zip, source_zip)
    else:
        logging.info('downloading rule source file...')
        response = requests.get(source_repo_url, headers=headers)
        if response.status_code == 200:
            with open(source_zip, 'wb') as file:
                file.write(response.content)
            logging.info('downloading rule source complete')
        else:
            logging.critical(f'downloading rule source error, error code {response.status_code}')
            exit(1)
    source_folder = os.path.join(current_dir, 'ios_rule_script')
    os.makedirs(source_folder, exist_ok=True)
    with zipfile.ZipFile(source_zip, 'r') as zip_ref:
        zip_ref.extractall(source_folder)
        logging.info(f"unzip asn files to {source_folder}")

class RuleSet(object):
    def __init__(self, domain, domain_keyword, domain_suffix, ip_cidr, process_name):
        self.version = 2
        self.rules = list()
        if len(domain) != 0 or len(domain_keyword) != 0 or len(domain_suffix) != 0 or len(ip_cidr) != 0:
            rule = dict()
            if len(domain) != 0:
                rule['domain'] = list(set(domain))
            if len(domain_keyword) != 0:
                rule['domain_keyword'] = list(set(domain_keyword))
            if len(domain_suffix) != 0:
                rule['domain_suffix'] = list(set(domain_suffix))
            if len(ip_cidr) != 0:
                rule['ip_cidr'] = list(set(ip_cidr))
            self.rules.append(rule)
        if len(process_name) != 0:
            rule = dict()
            rule['process_name'] = list(set(process_name))
            self.rules.append(rule)

skip_dirs = {'CGB'}
repo_slug = os.environ.get('GITHUB_REPOSITORY') or 'huime180/singbox_ruleset'

def rule_url(rel_dir):
    """rel_dir 为相对 rule/ 的目录路径，例如 'Game' 或 'Game/GameDownloadCN'。"""
    name = rel_dir.split('/')[-1]
    return ('https://raw.githubusercontent.com/{0}/main/rule/{1}/{2}.srs'
            .format(repo_slug, rel_dir, name),
            'https://cdn.jsdelivr.net/gh/{0}@main/rule/{1}/{2}.srs'
            .format(repo_slug, rel_dir, name))

def read_yaml_meta(source_file):
    """读取 yaml 头部的 # UPDATED / # <类型>: <数量>，返回 (更新时间, [(类型, 数量)])。"""
    updated = ''
    counts = []
    with open(source_file, 'r', encoding='utf-8') as file:
        for line in file:
            if not line.startswith('#'):
                break
            stripped = line.strip()
            if stripped.startswith('# UPDATED:'):
                updated = stripped[len('# UPDATED:'):].strip()
                continue
            matched = re.match(r'^# ([A-Z0-9\-]+): (\d+)$', stripped)
            if matched:
                counts.append((matched.group(1), int(matched.group(2))))
    return updated, counts

def build_readme(entry, rel_dir, updated, counts, subdirs, has_rules=True):
    """生成与上游 blackmatrix7 结构对齐的说明文件。

    has_rules 为 False 时表示该目录只有子目录、自身没有规则文件（上游的
    Assassin'sCreed、Cloud 就是这种容器目录），此时不输出统计与 .srs 链接。
    """
    github_url, cdn_url = rule_url(rel_dir)
    lines = [f'# {entry}', '']
    lines.append('## 说明')
    lines.append('')
    if has_rules:
        lines.append(f'{entry} 规则由上游 blackmatrix7/ios_rule_script 的 Clash 规则自动转换生成，'
                     '可直接用于 sing-box 的 rule_set。')
    else:
        lines.append(f'{entry} 是分类目录，上游该目录下没有自身的规则文件，'
                     '只包含下列子规则。')
    lines.append('')
    lines.append('分流规则是互联网公共服务的域名和 IP 地址汇总，所有数据均收集自互联网公开信息。')
    lines.append('')
    if has_rules:
        lines.append('## 规则统计')
        lines.append('')
        if updated:
            lines.append(f'上游最后更新时间：{updated}')
            lines.append('')
        lines.append('各类型规则统计：')
        lines.append('')
        lines.append('| 类型 | 数量(条) |')
        lines.append('| ---- | ---- |')
        for key, value in counts:
            lines.append(f'| {key} | {value} |')
        lines.append('')
        lines.append('## sing-box')
        lines.append('')
        lines.append('#### 使用说明')
        lines.append('')
        lines.append(f'- {entry}.srs，rule_set 的 format 使用 `binary`。')
        lines.append('')
        lines.append('#### 规则链接')
        lines.append('')
        lines.append('**Github**')
        lines.append('')
        lines.append(github_url)
        lines.append('')
        lines.append('**CDN**')
        lines.append('')
        lines.append(cdn_url)
        lines.append('')
    if subdirs:
        lines.append('## 子规则/排除规则')
        lines.append('')
        lines.append('当前分流规则，已包含以下子规则，除非特殊需求否则不建议重复引用：')
        lines.append('')
        lines.append('| 子规则 | 链接 |')
        lines.append('| ---- | ---- |')
        for sub in subdirs:
            sub_github, _ = rule_url(f'{rel_dir}/{sub}')
            lines.append(f'| {sub} | [Github]({sub_github}) |')
        lines.append('')
    lines.append('## 数据来源')
    lines.append('')
    lines.append('本规则集由上游仓库的 Clash 规则转换而来，原始规则及维护信息请查看对应目录：')
    lines.append('')
    lines.append(f'- https://github.com/blackmatrix7/ios_rule_script/tree/master/rule/Clash/{rel_dir}')
    lines.append('')
    return '\n'.join(lines)

def build_dump(entry, source_dir):
    """读取 Clash 源目录里的 yaml，返回 (json_data, 头部信息)。"""
    source_file = os.path.join(source_dir, f'{entry}.yaml')
    classical_file = os.path.join(source_dir, f'{entry}_Classical.yaml')
    if os.path.exists(classical_file):
        source_file = classical_file
    if not os.path.exists(source_file):
        return None, None

    updated, counts = read_yaml_meta(source_file)

    domain = list()
    domain_keyword = list()
    domain_suffix = list()
    ip_cidr = list()
    process_name = list()

    found_payload = False
    with open(source_file, 'r', encoding='utf-8') as file:
        for line in file:
            if 'payload:' in line.strip():
                found_payload = True
                continue
            if not found_payload:
                continue
            splits = line.strip()[2:].split(',')
            rule_type = splits[0]
            rule_content = splits[1]
            if rule_type == 'DOMAIN':
                domain.append(rule_content)
            elif rule_type == 'DOMAIN-SUFFIX':
                domain_suffix.append(rule_content)
            elif rule_type == 'DOMAIN-KEYWORD':
                domain_keyword.append(rule_content)
            elif rule_type == 'IP-CIDR' or rule_type == 'IP-CIDR6':
                ip_cidr.append(rule_content)
            elif rule_type == 'IP-ASN':
                if asn_ready:
                    asn = int(rule_content)
                    ip_cidr.extend(asn_v4[asn])
                    ip_cidr.extend(asn_v6[asn])
                else:
                    logging.warning('skip IP-ASN %s in %s (no asn data)', rule_content, entry)
            elif rule_type == 'PROCESS-NAME':
                process_name.append(rule_content)
            else:
                logging.warning(f'Unknown rule type { rule_type }')

    data = RuleSet(domain, domain_keyword, domain_suffix, ip_cidr, process_name)
    return data, (updated, counts)

def dump_source(entry, source_dir, target_dir, rel_dir, subdirs):
    """把单个分类写入 rule/<rel_dir>/<entry>.json 与 README.md。

    上游部分分类只有子目录、自身没有 yaml（例如 Assassin'sCreed、Cloud），
    这类目录不产出规则文件，只产出说明文件并列出子规则。
    """
    data, meta = build_dump(entry, source_dir)
    if data is None and not subdirs:
        logging.warning('no yaml found for %s, skip', rel_dir)
        return
    os.makedirs(target_dir, exist_ok=True)
    if data is not None:
        target_file = os.path.join(target_dir, f'{entry}.json')
        with open(target_file, 'w') as json_file:
            json.dump(data, json_file, default=lambda obj: obj.__dict__, sort_keys=True, indent=2)
    else:
        logging.info('no yaml for %s, only generate README with sub rules', rel_dir)
    updated, counts = meta if meta else ('', [])
    readme_file = os.path.join(target_dir, 'README.md')
    with open(readme_file, 'w', encoding='utf-8') as readme:
        readme.write(build_readme(entry, rel_dir, updated, counts, subdirs,
                                  has_rules=data is not None))

def translate_dir(name, source_dir, rel_dir):
    """递归处理一个分类目录：顶层分类自身出规则，子目录递归下去各自出规则。

    与上游 blackmatrix7 的结构保持一致，例如 rule/Game/Game.srs 与
    rule/Game/GameDownloadCN/GameDownloadCN.srs 同时存在。
    """
    target_dir = os.path.join(current_dir, 'rule', *rel_dir.split('/'))
    subs = sorted(d for d in os.listdir(source_dir)
                  if d not in skip_dirs and os.path.isdir(os.path.join(source_dir, d)))
    dump_source(name, source_dir, target_dir, rel_dir, subs)
    for sub in subs:
        translate_dir(sub, os.path.join(source_dir, sub), f'{rel_dir}/{sub}')

def translate_rule():
    source_folder = os.path.join(current_dir, 'ios_rule_script/ios_rule_script-master/rule/Clash')
    for entry in sorted(os.listdir(source_folder)):
        if entry in skip_dirs:
            continue
        source_dir = os.path.join(source_folder, entry)
        if not os.path.isdir(source_dir):
            continue
        translate_dir(entry, source_dir, entry)

    logging.info(f"finish translating clash rules")

extra_surge_conf = {}
def translate_extra():
    logging.info('translating extra surge rule...')
    target_folder = os.path.join(current_dir, 'rule')
    for k, v in extra_surge_conf.items():
        source_file = os.path.join(current_dir, f'{k}.conf')
        response = requests.get(v, headers=headers)
        if response.status_code == 200:
            with open(source_file, 'wb') as file:
                file.write(response.content)
            logging.info(f'downloading {k}.conf complete')
        else:
            logging.critical(f'downloading {k}.conf error, error code {response.status_code}')
            exit(1)

        domain = list()
        domain_keyword = list()
        domain_suffix = list()
        ip_cidr = list()
        process_name = list()

        with open(source_file, 'r', encoding='utf-8') as file:
            for line in file:
                if len(line.strip()) == 0:
                    continue
                if line.startswith('#'):
                    continue
                splits = line.strip().split(',')
                rule_type = splits[0]
                rule_content = splits[1]
                if rule_type == 'DOMAIN':
                    domain.append(rule_content)
                elif rule_type == 'DOMAIN-SUFFIX':
                    domain_suffix.append(rule_content)
                elif rule_type == 'DOMAIN-KEYWORD':
                    domain_keyword.append(rule_content)
                elif rule_type == 'IP-CIDR' or rule_type == 'IP-CIDR6':
                    ip_cidr.append(rule_content)    
                elif rule_type == 'IP-ASN':
                    if asn_ready:
                        asn = int(rule_content)
                        ip_cidr.extend(asn_v4[asn])
                        ip_cidr.extend(asn_v6[asn])
                    else:
                        logging.warning('skip IP-ASN %s in %s (no asn data)', rule_content, k)
                elif rule_type == 'PROCESS-NAME':
                    process_name.append(rule_content)
                elif rule_type == 'USER-AGENT':
                    pass
                else:
                    logging.warning(f'Unknown rule type { rule_type }')
        target_dir = os.path.join(target_folder, k)
        os.makedirs(target_dir, exist_ok=True)
        target_file = os.path.join(target_dir, f'{k}.json')        
        rule_content = RuleSet(domain, domain_keyword, domain_suffix, ip_cidr, process_name)
        with open(target_file, 'w') as json_file:
            json.dump(rule_content, json_file, default=lambda obj: obj.__dict__, sort_keys=True, indent=2)
        counts = [('DOMAIN', len(domain)), ('DOMAIN-KEYWORD', len(domain_keyword)),
                  ('DOMAIN-SUFFIX', len(domain_suffix)), ('IP-CIDR', len(ip_cidr)),
                  ('PROCESS-NAME', len(process_name))]
        counts = [(key, value) for key, value in counts if value]
        counts.append(('TOTAL', len(domain) + len(domain_keyword) + len(domain_suffix)
                       + len(ip_cidr) + len(process_name)))
        readme_file = os.path.join(target_dir, f'README.md')
        with open(readme_file, 'w', encoding='utf-8') as readme:
            readme.write(build_readme(k, k, '', counts, []))

def post_clean():
    for name in ('asn', 'ios_rule_script'):
        path = os.path.join(current_dir, name)
        if os.path.isdir(path):
            shutil.rmtree(path)
    for name in ('asn.zip', 'ios_rule_script.zip'):
        path = os.path.join(current_dir, name)
        if os.path.exists(path):
            os.remove(path)

def main():
    init()
    download_source_repo()
    translate_rule()
    translate_extra()
    post_clean()

if __name__ == "__main__":
    main()
