#!/usr/bin/env python3
"""
Telegram 智能加群工具 - 多账号并发版
功能：
1. 多账号同时加群
2. 自动删除已加入的群链接
3. 自动识别有效/无效链接
4. 实时统计报告
"""

import asyncio
import re
import os
import json
import random
from datetime import datetime
from typing import List, Dict, Optional
from telethon import TelegramClient, errors
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

# ===== 配置 =====
class Config:
    API_ID = 2040
    API_HASH = 'b18441a1ff607e10a989891a5462e627'
    SESSIONS_DIR = 'sessions'
    GROUPS_FILE = 'groups.txt'
    JOINED_FILE = 'joined.json'
    INVALID_FILE = 'invalid.json'
    STATS_FILE = 'stats.json'
    
    # 间隔设置（秒）
    INTERVAL_MIN = 30
    INTERVAL_MAX = 120
    BATCH_SIZE = 5
    BATCH_REST_MIN = 300
    BATCH_REST_MAX = 600
    
    # 每日限额（每个账号）
    DAILY_LIMIT = 30

# ===== 链接解析 =====
class GroupLinkParser:
    @staticmethod
    def parse_link(link: str) -> Optional[Dict]:
        """解析群链接"""
        link = link.strip()
        
        # 私有群邀请链接 (joinchat)
        match = re.match(r'https?://t\.me/joinchat/([A-Za-z0-9_-]+)', link)
        if match:
            return {'type': 'invite', 'hash': match.group(1), 'original': link}
        
        # 私有群邀请链接 (+ 格式)
        match = re.match(r'https?://t\.me/\+([A-Za-z0-9_-]+)', link)
        if match:
            return {'type': 'invite', 'hash': match.group(1), 'original': link}
        
        # App邀请链接
        match = re.match(r'tg://join\?invite=([A-Za-z0-9_-]+)', link)
        if match:
            return {'type': 'invite', 'hash': match.group(1), 'original': link}
        
        # 公开群链接
        match = re.match(r'https?://t\.me/([A-Za-z0-9_]+)', link)
        if match:
            return {'type': 'username', 'username': match.group(1), 'original': link}
        
        # @username 格式
        if link.startswith('@'):
            return {'type': 'username', 'username': link[1:], 'original': link}
        
        return None

# ===== 数据管理 =====
class DataManager:
    @staticmethod
    def load_json(file_path: str) -> dict:
        """加载JSON文件"""
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    @staticmethod
    def save_json(file_path: str, data: dict):
        """保存JSON文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    @staticmethod
    def load_groups() -> List[str]:
        """加载群链接列表"""
        if not os.path.exists(Config.GROUPS_FILE):
            return []
        
        with open(Config.GROUPS_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        groups = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                groups.append(line)
        
        return groups
    
    @staticmethod
    def save_groups(groups: List[str]):
        """保存群链接列表"""
        with open(Config.GROUPS_FILE, 'w', encoding='utf-8') as f:
            for group in groups:
                f.write(f"{group}\n")
    
    @staticmethod
    def remove_from_groups(link: str):
        """从群列表中删除已加入的群"""
        groups = DataManager.load_groups()
        groups = [g for g in groups if g.strip() != link.strip()]
        DataManager.save_groups(groups)
    
    @staticmethod
    def mark_joined(link: str, session: str):
        """标记为已加入"""
        joined = DataManager.load_json(Config.JOINED_FILE)
        if session not in joined:
            joined[session] = []
        
        if link not in joined[session]:
            joined[session].append(link)
        
        DataManager.save_json(Config.JOINED_FILE, joined)
        # 从群列表中删除
        DataManager.remove_from_groups(link)
    
    @staticmethod
    def mark_invalid(link: str, reason: str):
        """标记为无效链接"""
        invalid = DataManager.load_json(Config.INVALID_FILE)
        invalid[link] = {
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        }
        DataManager.save_json(Config.INVALID_FILE, invalid)
        # 从群列表中删除
        DataManager.remove_from_groups(link)
    
    @staticmethod
    def is_joined(link: str, session: str) -> bool:
        """检查是否已加入"""
        joined = DataManager.load_json(Config.JOINED_FILE)
        return link in joined.get(session, [])
    
    @staticmethod
    def is_invalid(link: str) -> bool:
        """检查是否为无效链接"""
        invalid = DataManager.load_json(Config.INVALID_FILE)
        return link in invalid

# ===== 单账号加群任务 =====
class AccountWorker:
    def __init__(self, session_name: str):
        self.session_name = session_name
        self.session_path = os.path.join(Config.SESSIONS_DIR, session_name)
        self.client = None
        self.stats = {
            'success': 0,
            'failed': 0,
            'invalid': 0,
            'skipped': 0
        }
    
    async def start(self):
        """启动客户端"""
        self.client = TelegramClient(self.session_path, Config.API_ID, Config.API_HASH)
        await self.client.connect()
        
        if not await self.client.is_user_authorized():
            print(f"❌ [{self.session_name}] Session未授权")
            return False
        
        me = await self.client.get_me()
        print(f"✅ [{self.session_name}] 登录成功: {me.first_name} +{me.phone}")
        return True
    
    async def join_group(self, link: str) -> tuple:
        """加入单个群
        
        Returns:
            (success: bool, status: str, message: str)
            status: 'success' | 'failed' | 'invalid' | 'skipped'
        """
        # 检查是否已加入
        if DataManager.is_joined(link, self.session_name):
            self.stats['skipped'] += 1
            return (False, 'skipped', '已加入')
        
        # 检查是否无效
        if DataManager.is_invalid(link):
            self.stats['skipped'] += 1
            return (False, 'skipped', '已标记为无效')
        
        # 解析链接
        parsed = GroupLinkParser.parse_link(link)
        if not parsed:
            DataManager.mark_invalid(link, '无法解析')
            self.stats['invalid'] += 1
            return (False, 'invalid', '无法解析')
        
        try:
            if parsed['type'] == 'invite':
                # 邀请链接
                result = await self.client(ImportChatInviteRequest(parsed['hash']))
                if hasattr(result, 'chats') and result.chats:
                    group_title = result.chats[0].title
                else:
                    group_title = 'Unknown'
                
                DataManager.mark_joined(link, self.session_name)
                self.stats['success'] += 1
                return (True, 'success', f'成功加入: {group_title}')
            
            elif parsed['type'] == 'username':
                # 公开群
                await self.client(JoinChannelRequest(parsed['username']))
                DataManager.mark_joined(link, self.session_name)
                self.stats['success'] += 1
                return (True, 'success', f'成功加入: @{parsed["username"]}')
        
        except errors.UserAlreadyParticipantError:
            # 已经在群里
            DataManager.mark_joined(link, self.session_name)
            self.stats['success'] += 1
            return (True, 'success', '已在群里')
        
        except errors.InviteHashExpiredError:
            DataManager.mark_invalid(link, '邀请链接已过期')
            self.stats['invalid'] += 1
            return (False, 'invalid', '邀请链接已过期')
        
        except errors.InviteHashInvalidError:
            DataManager.mark_invalid(link, '邀请链接无效')
            self.stats['invalid'] += 1
            return (False, 'invalid', '邀请链接无效')
        
        except errors.UsernameNotOccupiedError:
            DataManager.mark_invalid(link, '用户名不存在')
            self.stats['invalid'] += 1
            return (False, 'invalid', '用户名不存在')
        
        except errors.UsernameInvalidError:
            DataManager.mark_invalid(link, '用户名格式无效')
            self.stats['invalid'] += 1
            return (False, 'invalid', '用户名格式无效')
        
        except errors.ChannelsTooMuchError:
            self.stats['failed'] += 1
            return (False, 'failed', '加入的群太多了')
        
        except errors.FloodWaitError as e:
            self.stats['failed'] += 1
            return (False, 'failed', f'限流 {e.seconds}秒')
        
        except Exception as e:
            self.stats['failed'] += 1
            return (False, 'failed', f'{type(e).__name__}: {e}')
    
    async def stop(self):
        """停止客户端"""
        if self.client:
            await self.client.disconnect()

# ===== 多账号协调器 =====
class MultiAccountManager:
    def __init__(self, session_names: List[str]):
        self.session_names = session_names
        self.workers = []
        self.groups = []
        self.total_stats = {
            'success': 0,
            'failed': 0,
            'invalid': 0,
            'skipped': 0
        }
    
    async def run(self):
        """运行多账号加群任务"""
        print("=" * 60)
        print("Telegram 智能加群工具 - 多账号并发版")
        print("=" * 60)
        
        # 加载群列表
        self.groups = DataManager.load_groups()
        print(f"\n📋 待加入群数量: {len(self.groups)}")
        
        if not self.groups:
            print("⚠️  群列表为空！")
            return
        
        # 初始化所有worker
        print(f"\n🔐 启动 {len(self.session_names)} 个账号...")
        for session_name in self.session_names:
            worker = AccountWorker(session_name)
            if await worker.start():
                self.workers.append(worker)
        
        if not self.workers:
            print("❌ 没有可用的账号！")
            return
        
        print(f"✅ {len(self.workers)} 个账号准备就绪\n")
        
        # 分配任务（轮询）
        tasks = []
        for idx, link in enumerate(self.groups):
            worker = self.workers[idx % len(self.workers)]
            tasks.append(self.process_group(worker, link, idx + 1))
        
        # 并发执行
        await asyncio.gather(*tasks)
        
        # 关闭所有worker
        for worker in self.workers:
            await worker.stop()
        
        # 统计总结
        self.print_summary()
    
    async def process_group(self, worker: AccountWorker, link: str, idx: int):
        """处理单个群（带间隔）"""
        success, status, message = await worker.join_group(link)
        
        # 更新总统计
        self.total_stats[status] += 1
        
        # 打印结果
        emoji = {'success': '✅', 'failed': '❌', 'invalid': '⚠️', 'skipped': '⏭️'}[status]
        print(f"[{idx}/{len(self.groups)}] {emoji} [{worker.session_name}] {link[:50]}... - {message}")
        
        # 智能间隔
        if idx % Config.BATCH_SIZE == 0:
            rest = random.randint(Config.BATCH_REST_MIN, Config.BATCH_REST_MAX)
            print(f"⏸️  完成一批，休息 {rest} 秒...")
            await asyncio.sleep(rest)
        else:
            interval = random.randint(Config.INTERVAL_MIN, Config.INTERVAL_MAX)
            await asyncio.sleep(interval)
    
    def print_summary(self):
        """打印统计摘要"""
        print("\n" + "=" * 60)
        print("📊 统计摘要")
        print("=" * 60)
        
        # 总统计
        print(f"\n📈 总体:")
        print(f"  ✅ 成功: {self.total_stats['success']}")
        print(f"  ❌ 失败: {self.total_stats['failed']}")
        print(f"  ⚠️  无效: {self.total_stats['invalid']}")
        print(f"  ⏭️  跳过: {self.total_stats['skipped']}")
        
        # 各账号统计
        print(f"\n👥 各账号:")
        for worker in self.workers:
            print(f"  [{worker.session_name}]")
            print(f"    成功: {worker.stats['success']}, 失败: {worker.stats['failed']}, "
                  f"无效: {worker.stats['invalid']}, 跳过: {worker.stats['skipped']}")
        
        # 剩余群数量
        remaining = len(DataManager.load_groups())
        print(f"\n📋 剩余待加入群: {remaining}")

# ===== 主入口 =====
async def main():
    # 确保目录存在
    os.makedirs(Config.SESSIONS_DIR, exist_ok=True)
    
    # 扫描所有session文件
    sessions = []
    for file in os.listdir(Config.SESSIONS_DIR):
        if file.endswith('.session'):
            sessions.append(file.replace('.session', ''))
    
    if not sessions:
        print("❌ 未找到Session文件！")
        print(f"请将Session文件放到 {Config.SESSIONS_DIR}/ 目录")
        return
    
    print(f"🔍 发现 {len(sessions)} 个Session文件:")
    for s in sessions:
        print(f"  - {s}")
    
    # 创建管理器
    manager = MultiAccountManager(sessions)
    await manager.run()

if __name__ == '__main__':
    asyncio.run(main())
