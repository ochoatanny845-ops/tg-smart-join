#!/usr/bin/env python3
"""
Telegram 智能加群工具
- 支持导入Session账号
- 智能间隔加群（避免被封）
- 支持公开群/私有群链接
- 自动跳过已加入的群
- 完整日志记录
"""

import asyncio
import random
import re
import json
import os
import logging
from datetime import datetime
from typing import List, Dict, Optional
from telethon import TelegramClient, errors
from telethon.tl.types import Channel, Chat
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

# ===== 配置 =====
class Config:
    # API配置（从环境变量或这里配置）
    API_ID = int(os.getenv('API_ID', '你的API_ID'))
    API_HASH = os.getenv('API_HASH', '你的API_HASH')
    
    # 文件路径
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    SESSIONS_DIR = os.path.join(BASE_DIR, 'sessions')
    GROUPS_FILE = os.path.join(BASE_DIR, 'groups.txt')
    JOINED_FILE = os.path.join(BASE_DIR, 'joined.json')
    LOG_FILE = os.path.join(BASE_DIR, 'smart_join.log')
    
    # 智能间隔配置（秒）
    INTERVAL_MIN = 30   # 最小间隔30秒
    INTERVAL_MAX = 120  # 最大间隔120秒
    
    # 每批次配置
    BATCH_SIZE = 5          # 每批次加5个群
    BATCH_REST_MIN = 300    # 批次间隔5分钟
    BATCH_REST_MAX = 600    # 批次间隔10分钟
    
    # 每日限制
    DAILY_LIMIT = 30  # 每天最多加30个群（避免被封）
    
    # 创建必要目录
    os.makedirs(SESSIONS_DIR, exist_ok=True)

# ===== 日志配置 =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Config.LOG_FILE, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ===== 加群管理器 =====
class SmartJoinManager:
    def __init__(self):
        self.joined_data = self.load_joined_data()
        
    def load_joined_data(self) -> Dict:
        """加载已加入记录"""
        if os.path.exists(Config.JOINED_FILE):
            try:
                with open(Config.JOINED_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {'groups': {}, 'daily_count': 0, 'last_date': ''}
        return {'groups': {}, 'daily_count': 0, 'last_date': ''}
    
    def save_joined_data(self):
        """保存已加入记录"""
        with open(Config.JOINED_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.joined_data, f, ensure_ascii=False, indent=2)
    
    def is_joined(self, link: str) -> bool:
        """检查是否已加入"""
        return link in self.joined_data['groups']
    
    def mark_joined(self, link: str, group_title: str = ''):
        """标记已加入"""
        self.joined_data['groups'][link] = {
            'title': group_title,
            'joined_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.save_joined_data()
    
    def check_daily_limit(self) -> bool:
        """检查每日限额"""
        today = datetime.now().strftime('%Y-%m-%d')
        if self.joined_data['last_date'] != today:
            # 新的一天，重置计数
            self.joined_data['daily_count'] = 0
            self.joined_data['last_date'] = today
            self.save_joined_data()
            return True
        
        return self.joined_data['daily_count'] < Config.DAILY_LIMIT
    
    def increment_daily_count(self):
        """增加每日计数"""
        self.joined_data['daily_count'] += 1
        self.save_joined_data()

# ===== 群链接解析器 =====
class GroupLinkParser:
    @staticmethod
    def parse_link(link: str) -> Optional[Dict]:
        """解析群链接
        
        支持格式：
        1. https://t.me/joinchat/XXXXX (私有群邀请)
        2. https://t.me/+XXXXX (私有群邀请新格式)
        3. https://t.me/username (公开群)
        4. @username (公开群)
        """
        link = link.strip()
        
        # 私有群邀请链接 (joinchat)
        match = re.match(r'https?://t\.me/joinchat/([A-Za-z0-9_-]+)', link)
        if match:
            return {'type': 'invite', 'hash': match.group(1)}
        
        # 私有群邀请链接 (+ 格式)
        match = re.match(r'https?://t\.me/\+([A-Za-z0-9_-]+)', link)
        if match:
            return {'type': 'invite', 'hash': match.group(1)}
        
        # 公开群链接
        match = re.match(r'https?://t\.me/([A-Za-z0-9_]+)', link)
        if match:
            return {'type': 'username', 'username': match.group(1)}
        
        # @username 格式
        if link.startswith('@'):
            return {'type': 'username', 'username': link[1:]}
        
        logger.warning(f"无法解析链接: {link}")
        return None

# ===== 智能加群器 =====
class SmartJoiner:
    def __init__(self, session_name: str):
        self.session_path = os.path.join(Config.SESSIONS_DIR, session_name)
        self.client = None
        self.manager = SmartJoinManager()
        
    async def start(self):
        """启动客户端"""
        logger.info(f"正在启动客户端: {os.path.basename(self.session_path)}")
        self.client = TelegramClient(
            self.session_path,
            Config.API_ID,
            Config.API_HASH
        )
        await self.client.connect()
        
        if not await self.client.is_user_authorized():
            logger.error("Session未授权，请先登录！")
            return False
        
        me = await self.client.get_me()
        logger.info(f"✅ 登录成功: {me.first_name} (@{me.username or 'None'}) {me.phone}")
        return True
    
    async def join_group(self, link: str) -> bool:
        """加入单个群"""
        # 检查是否已加入
        if self.manager.is_joined(link):
            logger.info(f"⏭️  已加入，跳过: {link}")
            return False
        
        # 检查每日限额
        if not self.manager.check_daily_limit():
            logger.warning(f"⚠️  已达到每日限额 ({Config.DAILY_LIMIT}个群)")
            return False
        
        # 解析链接
        parsed = GroupLinkParser.parse_link(link)
        if not parsed:
            return False
        
        try:
            group_title = ''
            
            if parsed['type'] == 'invite':
                # 私有群邀请
                result = await self.client(ImportChatInviteRequest(parsed['hash']))
                if hasattr(result, 'chats') and result.chats:
                    group_title = result.chats[0].title
                logger.info(f"✅ 成功加入私有群: {group_title} ({link})")
                
            elif parsed['type'] == 'username':
                # 公开群
                entity = await self.client.get_entity(parsed['username'])
                if isinstance(entity, (Channel, Chat)):
                    await self.client(JoinChannelRequest(entity))
                    group_title = entity.title
                    logger.info(f"✅ 成功加入公开群: {group_title} (@{parsed['username']})")
                else:
                    logger.warning(f"⚠️  目标不是群组: {parsed['username']}")
                    return False
            
            # 标记已加入
            self.manager.mark_joined(link, group_title)
            self.manager.increment_daily_count()
            return True
            
        except errors.FloodWaitError as e:
            logger.error(f"❌ 触发限流，需要等待 {e.seconds} 秒")
            logger.info(f"⏸️  等待 {e.seconds} 秒后继续...")
            await asyncio.sleep(e.seconds)
            return False
            
        except errors.InviteHashExpiredError:
            logger.error(f"❌ 邀请链接已过期: {link}")
            return False
            
        except errors.InviteHashInvalidError:
            logger.error(f"❌ 邀请链接无效: {link}")
            return False
            
        except errors.UserAlreadyParticipantError:
            logger.info(f"ℹ️  已经在群里了: {link}")
            self.manager.mark_joined(link)
            return False
            
        except errors.ChannelPrivateError:
            logger.error(f"❌ 群组已私有或被封禁: {link}")
            return False
            
        except Exception as e:
            logger.error(f"❌ 加入失败: {link} - {e}")
            return False
    
    async def join_groups_from_file(self, groups_file: str):
        """从文件批量加群"""
        if not os.path.exists(groups_file):
            logger.error(f"群列表文件不存在: {groups_file}")
            return
        
        # 读取群链接
        with open(groups_file, 'r', encoding='utf-8') as f:
            links = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        logger.info(f"📋 读取到 {len(links)} 个群链接")
        
        # 过滤已加入的群
        pending_links = [link for link in links if not self.manager.is_joined(link)]
        logger.info(f"📊 待加入: {len(pending_links)} 个群 | 已加入: {len(links) - len(pending_links)} 个群")
        
        if not pending_links:
            logger.info("✅ 所有群都已加入！")
            return
        
        # 批量加群
        total = len(pending_links)
        success_count = 0
        
        for idx, link in enumerate(pending_links, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"进度: {idx}/{total} ({idx*100//total}%)")
            logger.info(f"今日已加: {self.manager.joined_data['daily_count']}/{Config.DAILY_LIMIT}")
            
            # 检查每日限额
            if not self.manager.check_daily_limit():
                logger.warning("⚠️  已达到每日限额，明天再来吧！")
                break
            
            # 加群
            success = await self.join_group(link)
            if success:
                success_count += 1
            
            # 智能间隔
            if idx < total:  # 不是最后一个
                # 每批次间隔
                if idx % Config.BATCH_SIZE == 0:
                    rest_time = random.randint(Config.BATCH_REST_MIN, Config.BATCH_REST_MAX)
                    logger.info(f"⏸️  完成一批次，休息 {rest_time} 秒...")
                    await asyncio.sleep(rest_time)
                else:
                    # 普通间隔
                    interval = random.randint(Config.INTERVAL_MIN, Config.INTERVAL_MAX)
                    logger.info(f"⏸️  等待 {interval} 秒后继续...")
                    await asyncio.sleep(interval)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🎉 加群完成！")
        logger.info(f"✅ 成功: {success_count} 个")
        logger.info(f"⏭️  跳过: {len(pending_links) - success_count} 个")
        logger.info(f"📊 今日已加: {self.manager.joined_data['daily_count']}/{Config.DAILY_LIMIT}")
    
    async def stop(self):
        """停止客户端"""
        if self.client:
            await self.client.disconnect()
            logger.info("客户端已断开")

# ===== 主程序 =====
async def main():
    print("""
╔══════════════════════════════════════════════════╗
║     Telegram 智能加群工具 v1.0                   ║
║     - 智能间隔，避免被封                          ║
║     - 自动跳过已加入群组                          ║
║     - 每日限额保护                                ║
╚══════════════════════════════════════════════════╝
    """)
    
    # 检查配置
    if Config.API_ID == 0 or Config.API_HASH == '你的API_HASH':
        print("❌ 请先配置 API_ID 和 API_HASH！")
        print("\n方法1: 修改 smart_join.py 中的配置")
        print("方法2: 设置环境变量 API_ID 和 API_HASH")
        return
    
    # 选择Session
    sessions = [f for f in os.listdir(Config.SESSIONS_DIR) if f.endswith('.session')]
    
    if not sessions:
        print(f"❌ 没有找到Session文件！")
        print(f"请将 .session 文件放到: {Config.SESSIONS_DIR}")
        return
    
    print("\n可用的Session账号：")
    for idx, session in enumerate(sessions, 1):
        print(f"  {idx}. {session}")
    
    choice = input(f"\n请选择账号 (1-{len(sessions)}): ").strip()
    try:
        session_name = sessions[int(choice) - 1].replace('.session', '')
    except:
        print("❌ 无效的选择！")
        return
    
    # 检查群列表文件
    if not os.path.exists(Config.GROUPS_FILE):
        print(f"\n❌ 群列表文件不存在: {Config.GROUPS_FILE}")
        print("正在创建示例文件...")
        with open(Config.GROUPS_FILE, 'w', encoding='utf-8') as f:
            f.write("""# Telegram 群链接列表
# 每行一个链接，支持以下格式：
# 1. https://t.me/joinchat/XXXXX (私有群)
# 2. https://t.me/+XXXXX (私有群新格式)
# 3. https://t.me/username (公开群)
# 4. @username (公开群)

# 示例：
# https://t.me/example_group
# @another_group
# https://t.me/+ABC123xyz
""")
        print(f"✅ 已创建示例文件: {Config.GROUPS_FILE}")
        print("请编辑该文件，添加群链接后重新运行！")
        return
    
    # 启动加群
    joiner = SmartJoiner(session_name)
    
    try:
        if await joiner.start():
            await joiner.join_groups_from_file(Config.GROUPS_FILE)
    finally:
        await joiner.stop()

if __name__ == '__main__':
    asyncio.run(main())
