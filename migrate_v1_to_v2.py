#!/usr/bin/env python3
"""
迁移工具：从v1.0升级到v2.0
"""
import os
import json
from datetime import datetime

# 文件路径
OLD_JOINED = 'joined.json'
NEW_JOINED = 'joined_v2.json'
BACKUP_FILE = f'joined_v1_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'

def migrate():
    """迁移joined.json格式"""
    
    # 备份旧文件
    if os.path.exists(OLD_JOINED):
        print(f"📂 发现旧版joined.json")
        
        with open(OLD_JOINED, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
        
        # 保存备份
        with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
            json.dump(old_data, f, indent=2, ensure_ascii=False)
        print(f"✅ 已备份到: {BACKUP_FILE}")
        
        # 检查是否是v1.0格式
        if 'groups' in old_data and 'daily_count' in old_data:
            print("⚠️  这是v1.0配置文件，不是加群记录！")
            print(f"   daily_count: {old_data.get('daily_count', 0)}")
            print(f"   last_date: {old_data.get('last_date', 'Unknown')}")
            
            # 创建空的v2.0格式
            new_data = {}
            
            with open(OLD_JOINED, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, indent=2, ensure_ascii=False)
            
            print("✅ 已清空joined.json，准备v2.0格式")
            print("📝 v2.0格式示例:")
            print('   {')
            print('     "92XXXXX": ["https://t.me/group1", "https://t.me/group2"],')
            print('     "86XXXXX": ["https://t.me/groupA"]')
            print('   }')
        else:
            print("✅ 格式未知，已备份")
    else:
        print("📂 未找到joined.json，将创建新文件")
        with open(OLD_JOINED, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        print("✅ 已创建空的joined.json")

if __name__ == '__main__':
    print("=" * 60)
    print("Telegram智能加群工具 - v1.0 → v2.0 迁移")
    print("=" * 60)
    print()
    
    migrate()
    
    print()
    print("=" * 60)
    print("✅ 迁移完成！")
    print("现在可以运行: python smart_join_gui_v2.py")
    print("=" * 60)
