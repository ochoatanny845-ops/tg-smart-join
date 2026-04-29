#!/usr/bin/env python3
"""
批量转换工具：把公开链接转成需要手动获取邀请链接的提示
"""

import sys

def convert_links(input_file, output_file):
    """转换群链接格式"""
    
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    converted = []
    skipped = []
    
    for line in lines:
        line = line.strip()
        
        if not line or line.startswith('#'):
            converted.append(line)
            continue
        
        # 检查是否是邀请链接
        if 'https://t.me/+' in line or 'https://t.me/joinchat/' in line:
            converted.append(line)  # 保留邀请链接
        elif line.startswith('@') or 'https://t.me/' in line:
            # 公开链接需要手动转换
            skipped.append(line)
            converted.append(f"# TODO: 需要获取邀请链接 - {line}")
        else:
            converted.append(line)
    
    # 保存转换结果
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(converted))
    
    print(f"✅ 转换完成！")
    print(f"📊 统计：")
    print(f"   - 总链接数: {len(lines)}")
    print(f"   - 需要转换: {len(skipped)} 个")
    print(f"   - 已是邀请链接: {len(converted) - len(skipped)} 个")
    print(f"\n⚠️  需要手动转换的链接：")
    for link in skipped[:10]:  # 只显示前10个
        print(f"   {link}")
    if len(skipped) > 10:
        print(f"   ... 还有 {len(skipped) - 10} 个")
    
    print(f"\n💡 如何获取邀请链接：")
    print(f"   1. 用主账号打开群组")
    print(f"   2. 点击群名 → '邀请链接'")
    print(f"   3. 复制链接（https://t.me/+XXXXX）")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        input_file = 'groups.txt'
        output_file = 'groups_converted.txt'
    else:
        input_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else 'groups_converted.txt'
    
    convert_links(input_file, output_file)
