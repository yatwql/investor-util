#!/usr/bin/env python3
"""
场景-测试文件覆盖率映射验证脚本。

用法：
    python scripts/validate_coverage_map.py            # 完整验证
    python scripts/validate_coverage_map.py --summary  # 仅输出汇总统计
    python scripts/validate_coverage_map.py --update   # 更新映射文件中的覆盖状态

功能：
    1. 扫描 src/test/ 中所有 Test 类，建立测试清单
    2. 对比 docs-stm/plan/test-coverage-map.md 中声明的映射
    3. 报告缺失的测试类/文件、多余的声明、状态差异
"""

import argparse
import glob
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DIR = os.path.join(PROJECT_ROOT, "src", "test")
COVERAGE_MAP_FILE = os.path.join(PROJECT_ROOT, "docs-stm", "plan", "test-coverage-map.md")


def scan_test_classes(test_dir=None):
    """扫描测试目录，返回 {file: [class_name, ...]} 映射"""
    if test_dir is None:
        test_dir = TEST_DIR

    if not os.path.isdir(test_dir):
        print(f"[!] 测试目录不存在: {test_dir}")
        return {}

    result = {}
    pattern = re.compile(r'^\s*class\s+(Test\w+)')

    for f in sorted(glob.glob(os.path.join(test_dir, "test_*.py"))):
        basename = os.path.basename(f)
        classes = []
        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                m = pattern.match(line)
                if m:
                    classes.append(m.group(1))
        if classes:
            result[basename] = classes

    return result


def parse_coverage_map(map_file=None):
    """解析覆盖映射文件，返回 [(scenario, status, location, note), ...]"""
    if map_file is None:
        map_file = COVERAGE_MAP_FILE

    if not os.path.isfile(map_file):
        print(f"[!] 映射文件不存在: {map_file}")
        return [], []

    entries = []
    errors = []

    with open(map_file, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    # 尝试解析表格行，跳过表头分隔线
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("| **") or stripped.startswith("|**"):
            in_table = True
            # 数据行: | **S1: xxx** | ✅/◐/❌ | `file::class` | 说明 |
            parts = [p.strip() for p in stripped.split("|")]
            # parts[0] 是空（行首 | 之前），parts[1] 是场景名，parts[2] 是状态，parts[3] 是位置，parts[4] 是说明
            if len(parts) >= 5:
                scenario = parts[1].strip("* ")
                status = parts[2].strip("* ")
                location = parts[3].strip("` ").strip()
                note = parts[4].strip() if len(parts) > 4 else ""
                entries.append((scenario, status, location, note))
        elif in_table and not stripped.startswith("|"):
            in_table = False  # 离开表格区域

    return entries, errors


def parse_location(location):
    """
    解析 location 字段，返回 (files, classes) 列表。

    支持格式：
    - `test_file.py::TestClass` → 单个文件+类
    - `test_file.py::TestClass`（含注释）→ 去掉括号注释
    - `test_file.py::TestClass1`、`TestClass2` → 共享文件的多个类
    - `test_file.py` + `test_file2.py` → 加号多文件
    - `test_file.py` → 仅文件
    """
    # 去掉括号注释（中文/英文括号中的附加说明）
    location_clean = re.sub(r'[（(][^）)]*[）)]', '', location).strip()

    result = []  # [(file, class_or_None), ...]
    current_file = None

    # 按中文顿号、中文逗号、加号分割
    parts = re.split(r'[、，,+]\s*', location_clean)

    for part in parts:
        # 去除首尾反引号和空白
        part = part.strip().strip('`').strip()
        if not part:
            continue
        # 跳过纯文字描述（不含.py也不含 ::）
        is_code_ref = '.py' in part or '::' in part
        if not is_code_ref:
            continue
        if '::' in part:
            # 取第一个 :: 分割，兼容 file::class::method
            sep = part.index('::')
            f = part[:sep].strip().strip('`').strip()
            cls_method = part[sep + 2:].strip().strip('`').strip()
            # 如果还有 ::，只取类名（忽略方法名）
            cls = cls_method.split('::')[0].strip().strip('`').strip()
            current_file = f
            result.append((f, cls))
        elif part.endswith('.py'):
            part = part.strip('`').strip()
            current_file = part
            result.append((part, None))
        elif current_file:
            # 没有::也没有.py后缀，但含有代码引用字样→认为是上一个文件的类延续
            part = part.strip('`').strip()
            result.append((current_file, part))

    return result


def validate_entries(entries, test_classes):
    """
    验证映射条目，返回 (passed, warnings, errors) 三组。
    """
    passed = []
    warnings = []
    errors_validation = []

    for scenario, status, location, note in entries:
        if not location or location == "—":
            if status.startswith("❌"):
                passed.append((scenario, status, location, "未覆盖，合理"))
            else:
                warnings.append((scenario, status, location, "已声明但无测试位置"))
            continue

        refs = parse_location(location)

        if not refs:
            warnings.append((scenario, status, location, "无法解析测试位置"))
            continue

        # 检查文件是否存在
        missing_files = []
        class_errors = []
        for f, cls in refs:
            if f not in test_classes:
                if f not in missing_files:
                    missing_files.append(f)
                continue
            if cls:
                if cls in test_classes[f]:
                    continue
                # 模糊匹配
                matched = [c for c in test_classes[f] if cls.lower() in c.lower()]
                if not matched:
                    class_errors.append(f"{f}::{cls}")

        if missing_files:
            errors_validation.append(
                (scenario, status, location, f"文件不存在: {missing_files}"))
        elif class_errors:
            errors_validation.append(
                (scenario, status, location, f"类不存在: {class_errors}"))
        else:
            passed.append((scenario, status, location, "验证通过"))

    return passed, warnings, errors_validation


def print_report(passed, warnings, errors_validation):
    """输出验证报告"""
    total = len(passed) + len(warnings) + len(errors_validation)

    env_encoding = sys.stdout.encoding or "utf-8"

    def u(text):
        """安全输出 Unicode，GBK 环境下降级"""
        try:
            text.encode(env_encoding)
            return text
        except UnicodeEncodeError:
            mapping = {
                "✅": "[OK]",
                "⚠": "[WARN]",
                "❌": "[ERR]",
                "◐": "[PARTIAL]",
                "—": "--",
                "•": "*",
                "️": "",
            }
            for k, v in mapping.items():
                text = text.replace(k, v)
            return text

    print(u(f"{'='*60}"))
    print(u(f"  覆盖率映射验证报告"))
    print(u(f"{'='*60}"))
    print(u(f"  总条目: {total}"))
    print(u(f"  [OK] 通过: {len(passed)}"))
    print(u(f"  [WARN] 警告: {len(warnings)}"))
    print(u(f"  [ERR] 错误: {len(errors_validation)}"))
    print(u(f"{'='*60}"))

    if warnings:
        print(u(f"\n[WARN] 警告 ({len(warnings)}):"))
        for s, st, loc, msg in warnings:
            print(u(f"  * {s} [{st}] -- {msg} (位置: {loc})"))

    if errors_validation:
        print(u(f"\n[ERR] 错误 ({len(errors_validation)}):"))
        for s, st, loc, msg in errors_validation:
            print(u(f"  * {s} [{st}] -- {msg}"))


def main():
    parser = argparse.ArgumentParser(description="验证测试覆盖率映射")
    parser.add_argument("--summary", action="store_true", help="仅输出汇总统计")
    parser.add_argument("--update", action="store_true", help="更新映射中的覆盖状态")
    args = parser.parse_args()

    # 扫描测试文件
    test_classes = scan_test_classes()
    if not test_classes:
        print("[!] 未找到测试文件")
        sys.exit(1)

    if args.summary:
        total_classes = sum(len(cls) for cls in test_classes.values())
        print(f"测试文件数: {len(test_classes)}")
        print(f"测试类数: {total_classes}")
        for f, cls in sorted(test_classes.items()):
            cls_list = ', '.join(cls[:5])
            suffix = '...' if len(cls) > 5 else ''
            print(f"  {f}: {len(cls)} 个类 -- {cls_list}{suffix}")
        return

    # 解析映射
    entries, parse_errors = parse_coverage_map()

    # 验证
    passed, warnings, errors_validation = validate_entries(entries, test_classes)
    print_report(passed, warnings, errors_validation)

    if errors_validation:
        sys.exit(1)


if __name__ == "__main__":
    main()
