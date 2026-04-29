#!/usr/bin/env python3
"""
测试单个群加入 - 诊断工具
"""
import asyncio
from telethon import TelegramClient, errors
from telethon.tl.functions.contacts import ResolveUsernameRequest
from telethon.tl.functions.channels import JoinChannelRequest

API_ID = 2040
API_HASH = 'b18441a1ff607e10a989891a5462e627'
SESSION_PATH = 'sessions/573105312165'  # 你的session文件名
USERNAME = 'P_B_I_YKMS'

async def test_join():
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.connect()
    
    if not await client.is_user_authorized():
        print("❌ Session未授权")
        return
    
    me = await client.get_me()
    print(f"✅ 登录: {me.first_name} +{me.phone}")
    
    print(f"\n📝 测试加入: @{USERNAME}")
    
    try:
        # 方法1: ResolveUsername
        print("\n[方法1] 尝试 ResolveUsernameRequest...")
        result = await client(ResolveUsernameRequest(USERNAME))
        
        if result.chats:
            chat = result.chats[0]
            print(f"✅ 找到群组: {chat.title}")
            print(f"   ID: {chat.id}")
            print(f"   成员数: {getattr(chat, 'participants_count', '未知')}")
            
            # 尝试加入
            try:
                await client(JoinChannelRequest(chat))
                print(f"✅ 成功加入！")
            except errors.UserAlreadyParticipantError:
                print(f"ℹ️  已经在群里了")
            except Exception as e:
                print(f"❌ 加入失败: {e}")
        else:
            print("❌ 未找到群组")
            
    except errors.UsernameNotOccupiedError:
        print("❌ 用户名不存在")
    except errors.UsernameInvalidError:
        print("❌ 用户名格式无效")
    except Exception as e:
        print(f"❌ 错误: {type(e).__name__}: {e}")
    
    # 方法2: 尝试小写
    print(f"\n[方法2] 尝试小写 @{USERNAME.lower()}...")
    try:
        result = await client(ResolveUsernameRequest(USERNAME.lower()))
        if result.chats:
            print(f"✅ 小写可用！")
    except:
        print(f"❌ 小写也不行")
    
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(test_join())
