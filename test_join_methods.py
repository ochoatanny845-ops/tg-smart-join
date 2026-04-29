#!/usr/bin/env python3
"""
测试JoinChannelRequest的正确用法
"""
import asyncio
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import SessionPasswordNeededError

API_ID = 2040
API_HASH = 'b18441a1ff607e10a989891a5462e627'
SESSION_PATH = 'sessions/573105312165'

async def test():
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.connect()
    
    if not await client.is_user_authorized():
        print("❌ Session未授权")
        return
    
    me = await client.get_me()
    print(f"✅ 登录: {me.first_name} +{me.phone}")
    
    # 测试1: 直接传username字符串
    print("\n=== 测试1: 直接传username字符串 ===")
    try:
        await client(JoinChannelRequest('P_B_I_YKMS'))
        print("✅ 方法1成功: 直接传字符串")
    except Exception as e:
        print(f"❌ 方法1失败: {type(e).__name__}: {e}")
    
    # 测试2: 先get_entity，再传实体对象
    print("\n=== 测试2: 先get_entity，再传实体 ===")
    try:
        entity = await client.get_entity('P_B_I_YKMS')
        await client(JoinChannelRequest(entity))
        print("✅ 方法2成功: 先get_entity再传")
    except Exception as e:
        print(f"❌ 方法2失败: {type(e).__name__}: {e}")
    
    # 测试3: 传@username格式
    print("\n=== 测试3: 传@username格式 ===")
    try:
        await client(JoinChannelRequest('@P_B_I_YKMS'))
        print("✅ 方法3成功: @username格式")
    except Exception as e:
        print(f"❌ 方法3失败: {type(e).__name__}: {e}")
    
    # 测试4: 传小写
    print("\n=== 测试4: 传小写username ===")
    try:
        await client(JoinChannelRequest('p_b_i_ykms'))
        print("✅ 方法4成功: 小写username")
    except Exception as e:
        print(f"❌ 方法4失败: {type(e).__name__}: {e}")
    
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(test())
