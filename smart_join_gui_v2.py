#!/usr/bin/env python3
"""
Telegram 智能加群工具 - 改进版GUI
功能：
1. 显示账号列表（手机号、名字、状态、统计）
2. 多账号选择加群
3. 放大字体
4. 实时统计
"""

import asyncio
import re
import os
import json
import random
import threading
from datetime import datetime
from typing import List, Dict, Optional
from tkinter import *
from tkinter import ttk, messagebox, filedialog, scrolledtext
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
    CONFIG_FILE = 'config.json'  # 配置文件
    
    # 每个账号加群后的间隔（秒）
    INTERVAL_MIN = 30
    INTERVAL_MAX = 120
    
    # 账号间加群间隔（秒，避免同一时间大量请求）
    ACCOUNT_INTERVAL_MIN = 5
    ACCOUNT_INTERVAL_MAX = 15
    
    BATCH_SIZE = 5
    BATCH_REST_MIN = 300
    BATCH_REST_MAX = 600
    DAILY_LIMIT = 30
    
    # 重复加群模式
    ALLOW_DUPLICATE = True  # True=所有账号加所有群，False=每个群只用一个账号
    
    @classmethod
    def load_config(cls):
        """从文件加载配置"""
        if os.path.exists(cls.CONFIG_FILE):
            try:
                with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    cls.INTERVAL_MIN = config.get('interval_min', cls.INTERVAL_MIN)
                    cls.INTERVAL_MAX = config.get('interval_max', cls.INTERVAL_MAX)
                    cls.ACCOUNT_INTERVAL_MIN = config.get('account_interval_min', cls.ACCOUNT_INTERVAL_MIN)
                    cls.ACCOUNT_INTERVAL_MAX = config.get('account_interval_max', cls.ACCOUNT_INTERVAL_MAX)
                    cls.BATCH_SIZE = config.get('batch_size', cls.BATCH_SIZE)
                    cls.BATCH_REST_MIN = config.get('batch_rest_min', cls.BATCH_REST_MIN)
                    cls.BATCH_REST_MAX = config.get('batch_rest_max', cls.BATCH_REST_MAX)
                    cls.DAILY_LIMIT = config.get('daily_limit', cls.DAILY_LIMIT)
                    cls.ALLOW_DUPLICATE = config.get('allow_duplicate', cls.ALLOW_DUPLICATE)
            except Exception as e:
                print(f"加载配置失败: {e}")
    
    @classmethod
    def save_config(cls):
        """保存配置到文件"""
        try:
            config = {
                'interval_min': cls.INTERVAL_MIN,
                'interval_max': cls.INTERVAL_MAX,
                'account_interval_min': cls.ACCOUNT_INTERVAL_MIN,
                'account_interval_max': cls.ACCOUNT_INTERVAL_MAX,
                'batch_size': cls.BATCH_SIZE,
                'batch_rest_min': cls.BATCH_REST_MIN,
                'batch_rest_max': cls.BATCH_REST_MAX,
                'daily_limit': cls.DAILY_LIMIT,
                'allow_duplicate': cls.ALLOW_DUPLICATE
            }
            with open(cls.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存配置失败: {e}")

# ===== 链接解析 =====
class GroupLinkParser:
    @staticmethod
    def parse_link(link: str) -> Optional[Dict]:
        link = link.strip()
        
        match = re.match(r'https?://t\.me/joinchat/([A-Za-z0-9_-]+)', link)
        if match:
            return {'type': 'invite', 'hash': match.group(1)}
        
        match = re.match(r'https?://t\.me/\+([A-Za-z0-9_-]+)', link)
        if match:
            return {'type': 'invite', 'hash': match.group(1)}
        
        match = re.match(r'tg://join\?invite=([A-Za-z0-9_-]+)', link)
        if match:
            return {'type': 'invite', 'hash': match.group(1)}
        
        match = re.match(r'https?://t\.me/([A-Za-z0-9_]+)', link)
        if match:
            return {'type': 'username', 'username': match.group(1)}
        
        if link.startswith('@'):
            return {'type': 'username', 'username': link[1:]}
        
        return None

# ===== 数据管理 =====
class DataManager:
    @staticmethod
    def load_json(file_path: str) -> dict:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    @staticmethod
    def save_json(file_path: str, data: dict):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    @staticmethod
    def get_joined_count(session_name: str) -> int:
        """获取账号已加入的群数量"""
        joined = DataManager.load_json(Config.JOINED_FILE)
        return len(joined.get(session_name, []))
    
    @staticmethod
    def mark_joined(session_name: str, link: str):
        """标记已加入"""
        joined = DataManager.load_json(Config.JOINED_FILE)
        if session_name not in joined:
            joined[session_name] = []
        if link not in joined[session_name]:
            joined[session_name].append(link)
        DataManager.save_json(Config.JOINED_FILE, joined)

# ===== 账号信息 =====
class AccountInfo:
    def __init__(self, session_name: str):
        self.session_name = str(session_name)  # 强制转换为字符串
        # 从session文件名提取手机号
        self.phone = self.extract_phone_from_session(self.session_name)
        self.name = ''
        self.status = '未知'
        self.joined_count = 0  # joined.json中的数量
        self.real_group_count = 0  # 真实群数量
        self.daily_limit = Config.DAILY_LIMIT
        self.is_authorized = False
    
    @staticmethod
    def extract_phone_from_session(session_name: str) -> str:
        """从session文件名提取手机号"""
        import re
        
        # 移除开头的+号（如果有）
        clean_name = session_name.lstrip('+')
        
        # 如果清理后的名称全是数字，就是手机号
        if clean_name.isdigit():
            return f'+{clean_name}'
        
        # 尝试提取连续数字（可能是手机号）
        match = re.search(r'\d{10,15}', clean_name)
        if match:
            return f'+{match.group()}'
        
        # 如果都失败，返回原session名称（可能带+）
        return session_name
    
    async def load_info(self):
        """加载账号信息"""
        session_path = os.path.join(Config.SESSIONS_DIR, self.session_name)
        
        # 检查session文件是否存在
        if not os.path.exists(session_path + '.session'):
            self.status = '❌ 文件不存在'
            self.is_authorized = False
            print(f"[DEBUG] Session文件不存在: {session_path}.session")
            return
        
        client = TelegramClient(session_path, Config.API_ID, Config.API_HASH)
        
        try:
            await client.connect()
            
            if await client.is_user_authorized():
                me = await client.get_me()
                self.phone = f'+{me.phone}' if me.phone else '未知'
                self.name = me.first_name or '未知'
                
                # 检查账号是否被限制/冻结
                try:
                    # 方法1: 尝试发送消息到"Saved Messages"（最准确！）
                    # 冻结账号无法发送任何消息，包括给自己
                    try:
                        # 发送当前时间到收藏夹（便于确认测试）
                        import time
                        from datetime import datetime
                        test_msg = f"[测试] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        msg = await client.send_message('me', test_msg)
                        print(f"[DEBUG] {self.session_name}: ✅ 已发送测试消息到收藏夹")
                        
                        # 等待1秒，让用户能看到（可选）
                        await asyncio.sleep(1)
                        
                        # 删除测试消息
                        await client.delete_messages('me', msg.id)
                        print(f"[DEBUG] {self.session_name}: 🗑️ 已删除测试消息")
                        
                        # 成功 → 账号正常
                        print(f"[DEBUG] {self.session_name}: 发送消息测试通过 - 账号正常")
                    except errors.ChatWriteForbiddenError:
                        # 无法发送消息 → 账号冻结
                        self.status = '⚠️ 账号受限/冻结'
                        self.is_authorized = False
                        self.real_group_count = 0
                        print(f"[DEBUG] {self.session_name}: ChatWriteForbiddenError - 账号冻结")
                        return
                    except errors.UserDeactivatedError:
                        self.status = '❌ 账号已被停用'
                        self.is_authorized = False
                        self.real_group_count = 0
                        return
                    except errors.UserDeactivatedBanError:
                        self.status = '❌ 账号已被封禁'
                        self.is_authorized = False
                        self.real_group_count = 0
                        return
                    except Exception as send_err:
                        error_msg = str(send_err).lower()
                        
                        # 检查是否是冻结相关错误
                        if 'frozen' in error_msg or 'deactivat' in error_msg or 'banned' in error_msg:
                            self.status = '⚠️ 账号受限/冻结'
                            self.is_authorized = False
                            self.real_group_count = 0
                            print(f"[DEBUG] {self.session_name}: 发送消息失败 - {send_err}")
                            return
                        
                        # 检查是否是invalid peer错误（冻结账号的常见表现！）
                        elif 'invalid peer' in error_msg or 'peer' in error_msg:
                            # 冻结账号无法发送消息到任何地方，包括收藏夹
                            self.status = '⚠️ 账号受限/冻结'
                            self.is_authorized = False
                            self.real_group_count = 0
                            print(f"[DEBUG] {self.session_name}: invalid Peer错误 - 账号冻结")
                            return
                        
                        else:
                            # 其他错误，可能是FloodWait，继续检查
                            print(f"[DEBUG] {self.session_name}: 发送消息出错（非冻结）- {send_err}")
                    
                    # 方法2: 检查User对象的restricted字段
                    if hasattr(me, 'restricted') and me.restricted:
                        self.status = '⚠️ 账号受限/冻结'
                        self.is_authorized = False
                        self.real_group_count = 0
                        print(f"[DEBUG] {self.session_name}: User.restricted = True")
                        return
                    
                    # 方法3: 检查FullUser的restricted字段
                    from telethon.tl.functions.users import GetFullUserRequest
                    try:
                        full_user = await client(GetFullUserRequest(me.id))
                        
                        # 检查full_user的限制标记
                        if hasattr(full_user, 'users') and full_user.users:
                            user = full_user.users[0]
                            if hasattr(user, 'restricted') and user.restricted:
                                self.status = '⚠️ 账号受限/冻结'
                                self.is_authorized = False
                                self.real_group_count = 0
                                print(f"[DEBUG] {self.session_name}: FullUser.restricted = True")
                                return
                    except Exception as e:
                        print(f"[DEBUG] {self.session_name}: GetFullUserRequest失败 - {e}")
                    
                    # 方法4: 尝试获取对话列表（被冻结的账号会报错）
                    dialogs = await client.get_dialogs(limit=1)
                    
                    # 统计真实群数量（只统计群组和超级群，不包括私聊和频道）
                    all_dialogs = await client.get_dialogs()
                    self.real_group_count = sum(1 for d in all_dialogs if d.is_group or d.is_channel)
                    
                    self.status = '✅ 正常'
                    self.is_authorized = True
                    
                except errors.AuthKeyUnregisteredError:
                    self.status = '❌ 账号已注销'
                    self.is_authorized = False
                    self.real_group_count = 0
                    
                except errors.UserDeactivatedError:
                    self.status = '❌ 账号已被停用'
                    self.is_authorized = False
                    self.real_group_count = 0
                    
                except errors.UserDeactivatedBanError:
                    self.status = '❌ 账号已被封禁'
                    self.is_authorized = False
                    self.real_group_count = 0
                    
                except Exception as check_error:
                    # 如果是冻结相关的错误
                    error_msg = str(check_error).lower()
                    if 'frozen' in error_msg or 'banned' in error_msg or 'deactivated' in error_msg:
                        self.status = '⚠️ 账号受限/冻结'
                        self.is_authorized = False
                        self.real_group_count = 0
                    else:
                        # 其他错误，可能是网络问题，先标记为正常
                        self.status = '✅ 正常'
                        self.is_authorized = True
                        print(f"[DEBUG] {self.session_name}: 检查限制时出错 - {check_error}")
                
                print(f"[DEBUG] {self.session_name}: {self.status} - {self.phone} ({self.name})")
            else:
                self.status = '❌ 未授权'
                self.is_authorized = False
                print(f"[DEBUG] {self.session_name}: 未授权")
            
            # 加载已加入群数
            self.joined_count = DataManager.get_joined_count(self.session_name)
            
        except errors.AuthKeyUnregisteredError:
            self.status = '❌ 账号已注销'
            self.is_authorized = False
            
        except errors.UserDeactivatedError:
            self.status = '❌ 账号已被停用'
            self.is_authorized = False
            
        except errors.UserDeactivatedBanError:
            self.status = '❌ 账号已被封禁'
            self.is_authorized = False
            
        except Exception as e:
            error_msg = str(e).lower()
            if 'frozen' in error_msg or 'banned' in error_msg or 'deactivated' in error_msg:
                self.status = '⚠️ 账号受限/冻结'
            else:
                self.status = f'❌ 错误: {e}'
            self.is_authorized = False
            print(f"[DEBUG] {self.session_name}: 错误 - {e}")
        
        finally:
            await client.disconnect()

# ===== 改进版GUI =====
class SmartJoinGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Telegram 智能加群工具 v2.0 - 改进版")
        self.root.geometry("1000x700")
        
        # 放大字体
        self.font_label = ("Arial", 12)         # 标签字体
        self.font_button = ("Arial", 14, "bold") # 按钮字体
        self.font_menu = ("Arial", 13, "bold")   # 菜单/标题字体
        self.font_log = ("Consolas", 11)        # 日志字体
        self.font_tab = ("Arial", 12, "bold")    # 标签页字体
        
        # 数据
        self.accounts = []  # AccountInfo列表
        self.selected_accounts = []  # 选中的账号
        self.is_running = False
        
        # 统计计数器
        self.total_success = 0
        self.total_failed = 0
        
        # 群发功能变量
        self.is_broadcasting = False
        self.broadcast_total_sent = 0
        self.broadcast_total_success = 0
        self.broadcast_total_failed = 0
        self.broadcast_groups = []  # 已加入的群组列表
        self.selected_broadcast_groups = []  # 选中的群组
        
        # 加载保存的配置
        Config.load_config()
        
        # 创建UI
        self.setup_ui()
        
        # 启动时快速加载（不检查状态）
        self.refresh_accounts_quick()
    
    def setup_ui(self):
        """创建UI"""
        
        # 创建Notebook（标签页）
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        # 配置标签页样式（放大字体）
        style = ttk.Style()
        style.configure('TNotebook.Tab', font=('Arial', 12, 'bold'), padding=[15, 8])
        
        # 标签页1: 主界面
        main_frame = Frame(self.notebook)
        self.notebook.add(main_frame, text="🏠 主界面")
        self.setup_main_tab(main_frame)
        
        # 标签页2: 群链接管理
        groups_frame = Frame(self.notebook)
        self.notebook.add(groups_frame, text="📋 群链接管理")
        self.setup_groups_tab(groups_frame)
        
        # 标签页3: 配置
        config_frame = Frame(self.notebook)
        self.notebook.add(config_frame, text="⚙️ 配置")
        self.setup_config_tab(config_frame)
        
        # 标签页4: 统计
        stats_frame = Frame(self.notebook)
        self.notebook.add(stats_frame, text="📊 统计")
        self.setup_stats_tab(stats_frame)
        
        # 标签页5: 群发消息（新增）
        broadcast_frame = Frame(self.notebook)
        self.notebook.add(broadcast_frame, text="📤 群发消息")
        self.setup_broadcast_tab(broadcast_frame)
    
    def setup_main_tab(self, parent):
        """主界面标签页"""
        
        # 顶部：账号列表
        account_frame = LabelFrame(parent, text="📱 账号列表", 
                                   font=self.font_menu, padx=10, pady=10)
        account_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # 账号表格
        columns = ('序号', '选择', '手机号', '名字', '状态', '已加群数', '实际群数')
        self.account_tree = ttk.Treeview(account_frame, columns=columns, 
                                        show='headings', height=8)
        
        # 列宽
        self.account_tree.column('序号', width=50, anchor=CENTER)
        self.account_tree.column('选择', width=50, anchor=CENTER)
        self.account_tree.column('手机号', width=130, anchor=CENTER)
        self.account_tree.column('名字', width=100, anchor=CENTER)
        self.account_tree.column('状态', width=140, anchor=CENTER)
        self.account_tree.column('已加群数', width=100, anchor=CENTER)
        self.account_tree.column('实际群数', width=100, anchor=CENTER)
        
        # 列标题
        for col in columns:
            self.account_tree.heading(col, text=col)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(account_frame, orient=VERTICAL, 
                                 command=self.account_tree.yview)
        self.account_tree.configure(yscrollcommand=scrollbar.set)
        
        self.account_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        # 双击切换选择
        self.account_tree.bind('<Double-1>', self.toggle_account_selection)
        
        # 右键菜单
        self.account_tree.bind('<Button-3>', self.show_account_menu)
        
        # 账号操作按钮
        account_btn_frame = Frame(parent)
        account_btn_frame.pack(fill=X, padx=10, pady=5)
        
        # 按钮字体（稍微缩小，但确保文字显示完整）
        btn_font = ("Arial", 10, "bold")
        
        Button(account_btn_frame, text="🔄 刷新列表", font=btn_font, 
               command=self.refresh_accounts_quick, 
               bg="#2196F3", fg="white", width=11, height=1).pack(side=LEFT, padx=2)
        
        Button(account_btn_frame, text="🔍 检查状态", font=btn_font, 
               command=lambda: threading.Thread(target=lambda: asyncio.run(self.check_accounts_status()), daemon=True).start(), 
               bg="#9C27B0", fg="white", width=11, height=1).pack(side=LEFT, padx=2)
        
        Button(account_btn_frame, text="➕ 导入Session", font=btn_font, 
               command=self.import_session, 
               bg="#4CAF50", fg="white", width=13, height=1).pack(side=LEFT, padx=2)
        
        Button(account_btn_frame, text="✅ 全选", font=btn_font, 
               command=self.select_all_accounts, 
               bg="#FF9800", fg="white", width=8, height=1).pack(side=LEFT, padx=2)
        
        Button(account_btn_frame, text="❌ 全不选", font=btn_font, 
               command=self.deselect_all_accounts, 
               bg="#9E9E9E", fg="white", width=9, height=1).pack(side=LEFT, padx=2)
        
        Button(account_btn_frame, text="🗑️ 删除选中", font=btn_font, 
               command=self.delete_selected_accounts, 
               bg="#F44336", fg="white", width=11, height=1).pack(side=LEFT, padx=2)
        
        Button(account_btn_frame, text="🗑️ 删除失效", font=btn_font, 
               command=self.delete_invalid_accounts, 
               bg="#f44336", fg="white", width=11, height=1).pack(side=LEFT, padx=2)
        
        Button(account_btn_frame, text="🔄 同步群数据", font=btn_font, 
               command=lambda: threading.Thread(target=lambda: asyncio.run(self.sync_group_data()), daemon=True).start(), 
               bg="#00BCD4", fg="white", width=13, height=1).pack(side=LEFT, padx=2)
        
        # 统计信息
        stats_frame = LabelFrame(parent, text="📊 统计信息", 
                                font=self.font_menu, padx=10, pady=5)
        stats_frame.pack(fill=X, padx=10, pady=5)
        
        self.stat_accounts = Label(stats_frame, text="可用账号: 0", 
                                   font=self.font_label)
        self.stat_accounts.grid(row=0, column=0, padx=10)
        
        self.stat_selected = Label(stats_frame, text="已选中: 0", 
                                  font=self.font_label, fg="blue")
        self.stat_selected.grid(row=0, column=1, padx=10)
        
        self.stat_groups = Label(stats_frame, text="待加群: 0", 
                                font=self.font_label, fg="orange")
        self.stat_groups.grid(row=0, column=2, padx=10)
        
        self.stat_success = Label(stats_frame, text="成功: 0", 
                                 font=self.font_label, fg="green")
        self.stat_success.grid(row=0, column=3, padx=10)
        
        self.stat_failed = Label(stats_frame, text="失败: 0", 
                                font=self.font_label, fg="red")
        self.stat_failed.grid(row=0, column=4, padx=10)
        
        # 控制按钮（缩小尺寸）
        control_frame = Frame(parent)
        control_frame.pack(fill=X, padx=10, pady=5)
        
        # 使用更小的字体
        ctrl_btn_font = ("Arial", 11, "bold")
        
        self.start_button = Button(control_frame, text="▶ 开始加群", 
                                   font=ctrl_btn_font, 
                                   command=self.start_join, 
                                   bg="#4CAF50", fg="white", width=10, height=1)
        self.start_button.pack(side=LEFT, padx=5)
        
        self.stop_button = Button(control_frame, text="⏸ 停止", 
                                  font=ctrl_btn_font, 
                                  command=self.stop_join, 
                                  bg="#f44336", fg="white", width=8, height=1, 
                                  state=DISABLED)
        self.stop_button.pack(side=LEFT, padx=5)
        
        # 进度条
        self.progress = ttk.Progressbar(parent, mode='determinate')
        self.progress.pack(fill=X, padx=10, pady=5)
        
        self.progress_label = Label(parent, text="就绪", font=self.font_label)
        self.progress_label.pack()
        
        # 日志
        log_frame = LabelFrame(parent, text="📜 运行日志", 
                              font=self.font_menu, padx=5, pady=5)
        log_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, 
                                                  font=self.font_log, wrap=WORD)
        self.log_text.pack(fill=BOTH, expand=True)
        
        # 日志颜色
        self.log_text.tag_config("INFO", foreground="black")
        self.log_text.tag_config("SUCCESS", foreground="green")
        self.log_text.tag_config("WARNING", foreground="orange")
        self.log_text.tag_config("ERROR", foreground="red")
    
    def setup_groups_tab(self, parent):
        """群链接管理标签页"""
        
        # 工具栏
        toolbar = Frame(parent)
        toolbar.pack(fill=X, padx=10, pady=5)
        
        Button(toolbar, text="📂 导入链接", font=self.font_button,
               command=self.import_groups, bg="#4CAF50", fg="white", width=12).pack(side=LEFT, padx=5)
        
        Button(toolbar, text="💾 保存", font=self.font_button,
               command=self.save_groups, bg="#2196F3", fg="white", width=10).pack(side=LEFT, padx=5)
        
        Button(toolbar, text="🗑️ 清空", font=self.font_button,
               command=self.clear_groups, bg="#f44336", fg="white", width=10).pack(side=LEFT, padx=5)
        
        # 数量显示
        self.groups_count_label = Label(toolbar, text="📊 群链接数: 0", font=self.font_button, fg="blue")
        self.groups_count_label.pack(side=RIGHT, padx=10)
        
        # 群链接文本框
        groups_frame = LabelFrame(parent, text="📋 群链接列表 (每行一个)", 
                                 font=self.font_menu, padx=5, pady=5)
        groups_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        self.groups_text = scrolledtext.ScrolledText(groups_frame, font=self.font_log, wrap=WORD)
        self.groups_text.pack(fill=BOTH, expand=True)
        
        # 加载群链接
        self.load_groups_text()
    
    def setup_config_tab(self, parent):
        """配置标签页"""
        
        config_frame = LabelFrame(parent, text="⚙️ 加群配置", 
                                 font=self.font_menu, padx=10, pady=10)
        config_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # 群间隔设置
        Label(config_frame, text="最小间隔(秒):", font=self.font_label).grid(row=0, column=0, sticky=W, pady=5)
        self.interval_min_var = IntVar(value=Config.INTERVAL_MIN)
        Entry(config_frame, textvariable=self.interval_min_var, font=self.font_label, width=10).grid(row=0, column=1, pady=5)
        
        Label(config_frame, text="最大间隔(秒):", font=self.font_label).grid(row=1, column=0, sticky=W, pady=5)
        self.interval_max_var = IntVar(value=Config.INTERVAL_MAX)
        Entry(config_frame, textvariable=self.interval_max_var, font=self.font_label, width=10).grid(row=1, column=1, pady=5)
        
        # 账号间隔设置（新增）
        Label(config_frame, text="账号间隔最小(秒):", font=self.font_label).grid(row=2, column=0, sticky=W, pady=5)
        self.account_interval_min_var = IntVar(value=Config.ACCOUNT_INTERVAL_MIN)
        Entry(config_frame, textvariable=self.account_interval_min_var, font=self.font_label, width=10).grid(row=2, column=1, pady=5)
        
        Label(config_frame, text="账号间隔最大(秒):", font=self.font_label).grid(row=3, column=0, sticky=W, pady=5)
        self.account_interval_max_var = IntVar(value=Config.ACCOUNT_INTERVAL_MAX)
        Entry(config_frame, textvariable=self.account_interval_max_var, font=self.font_label, width=10).grid(row=3, column=1, pady=5)
        
        Label(config_frame, text="批次大小:", font=self.font_label).grid(row=4, column=0, sticky=W, pady=5)
        self.batch_size_var = IntVar(value=Config.BATCH_SIZE)
        Entry(config_frame, textvariable=self.batch_size_var, font=self.font_label, width=10).grid(row=4, column=1, pady=5)
        
        Label(config_frame, text="批次休息最小(秒):", font=self.font_label).grid(row=5, column=0, sticky=W, pady=5)
        self.batch_rest_min_var = IntVar(value=Config.BATCH_REST_MIN)
        Entry(config_frame, textvariable=self.batch_rest_min_var, font=self.font_label, width=10).grid(row=5, column=1, pady=5)
        
        Label(config_frame, text="批次休息最大(秒):", font=self.font_label).grid(row=6, column=0, sticky=W, pady=5)
        self.batch_rest_max_var = IntVar(value=Config.BATCH_REST_MAX)
        Entry(config_frame, textvariable=self.batch_rest_max_var, font=self.font_label, width=10).grid(row=6, column=1, pady=5)
        
        Label(config_frame, text="每日限额:", font=self.font_label).grid(row=7, column=0, sticky=W, pady=5)
        self.daily_limit_var = IntVar(value=Config.DAILY_LIMIT)
        Entry(config_frame, textvariable=self.daily_limit_var, font=self.font_label, width=10).grid(row=7, column=1, pady=5)
        
        # 重复加群模式
        Label(config_frame, text="重复加群模式:", font=self.font_label).grid(row=8, column=0, sticky=W, pady=5)
        self.allow_duplicate_var = BooleanVar(value=Config.ALLOW_DUPLICATE)
        duplicate_frame = Frame(config_frame)
        duplicate_frame.grid(row=8, column=1, sticky=W, pady=5)
        Radiobutton(duplicate_frame, text="重复（所有号加所有群）", variable=self.allow_duplicate_var, 
                   value=True, font=self.font_label).pack(anchor=W)
        Radiobutton(duplicate_frame, text="不重复（每群只用一个号）", variable=self.allow_duplicate_var, 
                   value=False, font=self.font_label).pack(anchor=W)
        
        # 保存按钮
        Button(config_frame, text="💾 保存配置", font=self.font_button,
               command=self.save_config, bg="#4CAF50", fg="white", width=15).grid(row=9, column=0, columnspan=2, pady=20)
    
    def setup_stats_tab(self, parent):
        """统计标签页"""
        
        stats_frame = LabelFrame(parent, text="📊 加群统计", 
                                font=self.font_menu, padx=10, pady=10)
        stats_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # 统计文本
        self.stats_text = scrolledtext.ScrolledText(stats_frame, font=self.font_log, wrap=WORD)
        self.stats_text.pack(fill=BOTH, expand=True)
        
        # 刷新按钮
        Button(stats_frame, text="🔄 刷新统计", font=self.font_button,
               command=self.refresh_stats, bg="#2196F3", fg="white", width=15).pack(pady=10)
        
        # 加载统计
        self.refresh_stats()
    
    def load_groups_text(self):
        """加载群链接到文本框"""
        if os.path.exists(Config.GROUPS_FILE):
            with open(Config.GROUPS_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
                self.groups_text.delete('1.0', END)
                self.groups_text.insert('1.0', content)
        
        # 更新数量显示
        self.update_groups_count()
    
    def import_groups(self):
        """导入群链接"""
        file = filedialog.askopenfilename(
            title="选择群链接文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        
        if file:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.groups_text.delete('1.0', END)
                self.groups_text.insert('1.0', content)
                self.update_groups_count()
                self.log("✅ 导入群链接成功", "SUCCESS")
            except Exception as e:
                self.log(f"❌ 导入失败: {e}", "ERROR")
    
    def save_groups(self):
        """保存群链接"""
        content = self.groups_text.get('1.0', END)
        try:
            with open(Config.GROUPS_FILE, 'w', encoding='utf-8') as f:
                f.write(content)
            self.update_groups_count()
            self.log("✅ 保存成功", "SUCCESS")
            self.update_stats()
        except Exception as e:
            self.log(f"❌ 保存失败: {e}", "ERROR")
    
    def update_groups_count(self):
        """更新群链接数量显示"""
        content = self.groups_text.get('1.0', END)
        lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')]
        count = len(lines)
        self.groups_count_label.config(text=f"📊 群链接数: {count}")
    
    def clear_groups(self):
        """清空群链接"""
        if messagebox.askyesno("确认", "确定要清空所有群链接吗？"):
            self.groups_text.delete('1.0', END)
            self.update_groups_count()
            self.log("⚠️ 群链接已清空（未保存）", "WARNING")
    
    def save_config(self):
        """保存配置"""
        Config.INTERVAL_MIN = self.interval_min_var.get()
        Config.INTERVAL_MAX = self.interval_max_var.get()
        Config.ACCOUNT_INTERVAL_MIN = self.account_interval_min_var.get()  # 新增
        Config.ACCOUNT_INTERVAL_MAX = self.account_interval_max_var.get()  # 新增
        Config.BATCH_SIZE = self.batch_size_var.get()
        Config.BATCH_REST_MIN = self.batch_rest_min_var.get()
        Config.BATCH_REST_MAX = self.batch_rest_max_var.get()
        Config.DAILY_LIMIT = self.daily_limit_var.get()
        Config.ALLOW_DUPLICATE = self.allow_duplicate_var.get()
        
        # 保存到文件（持久化）
        Config.save_config()
        
        # 更新所有账号的daily_limit
        for account in self.accounts:
            account.daily_limit = Config.DAILY_LIMIT
        
        # 刷新账号列表显示
        self.refresh_accounts_quick()
        
        # 刷新统计标签页
        self.refresh_stats()
        
        mode = "重复加群" if Config.ALLOW_DUPLICATE else "不重复加群"
        self.log(f"✅ 配置已保存（模式: {mode}，账号间隔: {Config.ACCOUNT_INTERVAL_MIN}-{Config.ACCOUNT_INTERVAL_MAX}秒）", "SUCCESS")
        messagebox.showinfo("成功", f"配置已保存！\n模式: {mode}\n账号间隔: {Config.ACCOUNT_INTERVAL_MIN}-{Config.ACCOUNT_INTERVAL_MAX}秒")
    
    def refresh_stats(self):
        """刷新统计"""
        self.stats_text.delete('1.0', END)
        
        # 加载joined.json
        joined = DataManager.load_json(Config.JOINED_FILE)
        
        stats_text = "=" * 60 + "\n"
        stats_text += "📊 加群统计报告\n"
        stats_text += "=" * 60 + "\n\n"
        
        if not joined:
            stats_text += "暂无加群记录\n"
        else:
            # 兼容性检查：处理旧格式
            total_joined = 0
            for session_name, groups in joined.items():
                # 如果是旧格式（int），转换成新格式（list）
                if isinstance(groups, int):
                    total_joined += groups
                elif isinstance(groups, list):
                    total_joined += len(groups)
            
            stats_text += f"📈 总计: {len(joined)} 个账号，已加入 {total_joined} 个群\n\n"
            
            for session_name, groups in joined.items():
                # 获取账号信息
                account = next((acc for acc in self.accounts if acc.session_name == session_name), None)
                if account:
                    stats_text += f"👤 {account.phone} ({account.name})\n"
                else:
                    stats_text += f"👤 {session_name}\n"
                
                # 处理不同格式
                if isinstance(groups, int):
                    stats_text += f"   已加入群数: {groups}\n"
                    stats_text += f"   ⚠️  旧格式数据，无详细记录\n"
                elif isinstance(groups, list):
                    stats_text += f"   已加入群数: {len(groups)}\n"
                    stats_text += f"   最近5个群:\n"
                    for group in groups[-5:]:
                        stats_text += f"      - {group}\n"
                else:
                    stats_text += f"   ⚠️  数据格式错误\n"
                
                stats_text += "\n"
        
        self.stats_text.insert('1.0', stats_text)
    
    def refresh_accounts_quick(self):
        """快速刷新账号列表（不检查状态，只刷新统计）"""
        self.log("🔄 快速刷新账号列表...", "INFO")
        
        # 重新扫描Session文件
        if not os.path.exists(Config.SESSIONS_DIR):
            self.log("⚠️  sessions目录为空！", "WARNING")
            return
        
        # 移除.session后缀，得到session名称（确保是字符串）
        session_files = [str(f.replace('.session', '')) 
                        for f in os.listdir(Config.SESSIONS_DIR) 
                        if f.endswith('.session')]
        
        # 清空表格
        for item in self.account_tree.get_children():
            self.account_tree.delete(item)
        
        # 更新accounts列表
        old_accounts = {acc.session_name: acc for acc in self.accounts}
        self.accounts = []
        
        # 添加到表格（使用旧状态或默认状态）
        for idx, session_name in enumerate(session_files, start=1):
            # 标准化session名称（移除开头的+号，如果有的话）
            normalized_name = session_name.lstrip('+')
            
            # 尝试从旧账号中找（支持带+和不带+两种格式）
            account = old_accounts.get(session_name) or old_accounts.get(normalized_name) or old_accounts.get('+' + normalized_name)
            
            if account:
                # 使用旧数据，更新加群数
                account.session_name = session_name  # 更新为当前文件名
                account.joined_count = DataManager.get_joined_count(session_name)
            else:
                # 新账号，使用默认值（会自动从session名称提取手机号）
                account = AccountInfo(session_name)
                account.name = '未检查'
                account.status = '⚪ 未检查'
                account.joined_count = DataManager.get_joined_count(session_name)
            
            self.accounts.append(account)
            
            values = (
                str(idx),
                '☐',
                account.phone,
                account.name,
                account.status,
                f"{account.joined_count}/{account.daily_limit}",
                str(account.real_group_count) if account.real_group_count > 0 else '-'
            )
            # 添加前缀确保tags是字符串（快速刷新）
            self.account_tree.insert('', END, values=values, tags=(f'session_{account.session_name}',))
        
        # 更新统计
        self.update_stats()
        self.log(f"✅ 刷新完成！共 {len(self.accounts)} 个账号", "SUCCESS")
    
    async def check_accounts_status(self):
        """检查所有账号状态（并发10线程）"""
        # 如果有选中的账号，只检查选中的；否则检查全部
        if self.selected_accounts:
            accounts_to_check = [acc for acc in self.accounts if acc.session_name in self.selected_accounts]
            self.log(f"🔍 检查选中的账号状态（10线程并发）... 选中: {len(accounts_to_check)} 个", "INFO")
        else:
            accounts_to_check = self.accounts
            self.log(f"🔍 检查所有账号状态（10线程并发）... 总计: {len(accounts_to_check)} 个账号", "INFO")
        
        if not accounts_to_check:
            self.log("⚠️  没有账号需要检查！", "WARNING")
            return
        
        # 并发检查
        self.log(f"📡 开始连接Telegram服务器...", "INFO")
        
        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(10)
        
        async def check_one_account(account):
            async with semaphore:
                await account.load_info()
                # 检查完成后立即记录日志
                status_emoji = "✅" if account.is_authorized else "❌"
                if "⚠️" in account.status:
                    status_emoji = "⚠️"
                
                group_info = f" ({account.real_group_count}个群)" if account.real_group_count > 0 else ""
                self.log(f"{status_emoji} [{account.phone}] {account.name} - {account.status.replace('✅ ', '').replace('❌ ', '').replace('⚠️ ', '')}{group_info}", 
                         "SUCCESS" if account.is_authorized else "ERROR")
        
        # 创建任务列表
        tasks = [check_one_account(account) for account in accounts_to_check]
        
        self.log(f"⏳ 并发执行 {len(tasks)} 个检查任务...", "INFO")
        await asyncio.gather(*tasks)
        self.log(f"📥 所有任务完成，开始更新界面...", "INFO")
        
        # 统计
        total = len(self.accounts)
        authorized = 0
        unauthorized = 0
        updated = 0
        
        # 清空表格并重新添加（确保数据一致）
        for item in self.account_tree.get_children():
            self.account_tree.delete(item)
        
        # 重新添加所有账号（已检查过，有正确数据）
        for idx, account in enumerate(self.accounts, start=1):
            values = (
                str(idx),
                '☐',
                account.phone,
                account.name,
                account.status,
                f"{account.joined_count}/{account.daily_limit}",
                str(account.real_group_count)
            )
            # 添加前缀确保tags是字符串（检查状态后）
            self.account_tree.insert('', END, values=values, tags=(f'session_{account.session_name}',))
            
            # 统计
            if account.is_authorized:
                authorized += 1
            else:
                unauthorized += 1
            updated += 1
        
        # 更新统计
        self.update_stats()
        self.log(f"📊 更新了 {updated} 个账号的界面", "INFO")
        self.log(f"✅ 检查完成！正常: {authorized}, 失效: {unauthorized}, 总计: {total}", "SUCCESS")
    
    def toggle_account_selection(self, event):
        """切换账号选择状态"""
        item = self.account_tree.selection()[0]
        tag_with_prefix = self.account_tree.item(item)['tags'][0]
        session_name = tag_with_prefix.replace('session_', '')  # 去掉前缀
        
        # 切换选中状态
        current_values = list(self.account_tree.item(item)['values'])
        if current_values[1] == '☐':  # 注意：序号在索引0，选择框在索引1
            current_values[1] = '☑'
            if session_name not in self.selected_accounts:
                self.selected_accounts.append(session_name)
        else:
            current_values[1] = '☐'
            if session_name in self.selected_accounts:
                self.selected_accounts.remove(session_name)
        
        self.account_tree.item(item, values=current_values)
        self.update_stats()
    
    def show_account_menu(self, event):
        """显示右键菜单"""
        # 选中右键点击的项
        item = self.account_tree.identify_row(event.y)
        if not item:
            return
        
        self.account_tree.selection_set(item)
        
        # 创建菜单
        menu = Menu(self.root, tearoff=0, font=self.font_label)
        menu.add_command(label="🌐 登录Web版", command=lambda: self.login_web(item))
        
        # 显示菜单
        menu.post(event.x_root, event.y_root)
    
    def login_web(self, item):
        """登录Telegram Web版"""
        tag_with_prefix = self.account_tree.item(item)['tags'][0]
        session_name = tag_with_prefix.replace('session_', '')
        
        self.log(f"🌐 正在为 {session_name} 登录Web版...", "INFO")
        
        # 在后台线程执行
        threading.Thread(target=lambda: self._login_web_worker(session_name), daemon=True).start()
    
    def _login_web_worker(self, session_name: str):
        """Web登录工作线程（使用成功的GramJS方案）"""
        try:
            import sqlite3
            
            # Session文件路径
            session_path = os.path.join(Config.SESSIONS_DIR, session_name + '.session')
            
            if not os.path.exists(session_path):
                self.log(f"❌ Session文件不存在: {session_path}", "ERROR")
                return
            
            # 读取session数据
            conn = sqlite3.connect(session_path)
            cursor = conn.cursor()
            
            # 获取auth_key和dc_id
            cursor.execute("SELECT auth_key, dc_id, server_address, port FROM sessions")
            row = cursor.fetchone()
            
            if not row:
                self.log(f"❌ Session数据为空", "ERROR")
                conn.close()
                return
            
            auth_key_bytes, dc_id, server_address, port = row
            conn.close()
            
            # 转换为16进制字符串（Telegram Web格式）
            auth_key_hex = auth_key_bytes.hex()
            
            # 计算auth_key_fingerprint（前4个字节）
            fingerprint = auth_key_bytes[:4].hex()
            
            # 生成随机server_salt
            import random
            server_salt = ''.join(random.choice('0123456789abcdef') for _ in range(16))
            
            # 尝试使用Selenium自动化
            try:
                from selenium import webdriver
                from selenium.webdriver.chrome.options import Options
                import time
                
                # Chrome选项
                chrome_options = Options()
                chrome_options.add_argument('--incognito')  # 无痕模式
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                # 尝试启动Chrome
                self.log(f"🚀 启动Chrome无痕模式...", "INFO")
                
                driver = None
                # 方式1：本地驱动
                local_paths = [
                    r"C:\chromedriver\chromedriver.exe",
                    "chromedriver.exe",
                ]
                for path in local_paths:
                    if os.path.exists(path):
                        try:
                            from selenium.webdriver.chrome.service import Service
                            service = Service(path)
                            driver = webdriver.Chrome(service=service, options=chrome_options)
                            self.log(f"✅ 使用本地驱动: {path}", "INFO")
                            break
                        except:
                            continue
                
                # 方式2：系统PATH
                if not driver:
                    try:
                        driver = webdriver.Chrome(options=chrome_options)
                        self.log(f"✅ 使用系统驱动", "INFO")
                    except:
                        pass
                
                # 方式3：自动下载
                if not driver:
                    try:
                        from webdriver_manager.chrome import ChromeDriverManager
                        from selenium.webdriver.chrome.service import Service
                        self.log(f"⏳ 下载ChromeDriver（首次较慢）...", "INFO")
                        service = Service(ChromeDriverManager().install())
                        driver = webdriver.Chrome(service=service, options=chrome_options)
                        self.log(f"✅ 自动下载成功", "INFO")
                    except Exception as e:
                        self.log(f"❌ 无法启动Chrome: {e}", "ERROR")
                        return
                
                if not driver:
                    self.log(f"❌ 无法启动Chrome", "ERROR")
                    return
                
                # 打开Telegram Web A版
                self.log(f"📱 打开 Telegram Web A版...", "INFO")
                driver.get("https://web.telegram.org/a/")
                time.sleep(2)
                
                # 注入localStorage（使用成功的格式）
                self.log(f"🔑 注入认证数据...", "INFO")
                
                script = f"""
                // 核心认证数据（auth_key和server_salt必须用引号包裹！）
                localStorage.setItem('dc', '{dc_id}');
                localStorage.setItem('dc{dc_id}_auth_key', '"{auth_key_hex}"');
                localStorage.setItem('dc{dc_id}_server_salt', '"{server_salt}"');
                localStorage.setItem('auth_key_fingerprint', '"{fingerprint}"');
                
                // 用户认证信息
                const userAuth = {{
                    dcID: {dc_id},
                    id: "0"
                }};
                localStorage.setItem('user_auth', JSON.stringify(userAuth));
                
                // 其他必要字段
                localStorage.setItem('k_build', '589');
                localStorage.setItem('kz_version', '"K"');
                localStorage.setItem('number_of_accounts', '1');
                localStorage.setItem('server_time_offset', '0');
                localStorage.setItem('tt-multitab_1', '1');
                localStorage.setItem('loglevel', 'SILENT');
                
                // state_id和xt_instance
                const stateId = Math.floor(Math.random() * 0xFFFFFFFF) >>> 0;
                localStorage.setItem('state_id', stateId.toString());
                localStorage.setItem('xt_instance', JSON.stringify({{
                    id: Math.floor(Math.random() * 1e8),
                    idle: false,
                    time: Date.now()
                }}));
                
                // tgme_sync
                localStorage.setItem('tgme_sync', JSON.stringify({{
                    canRedirect: true,
                    ts: Math.floor(Date.now() / 1000)
                }}));
                
                console.log('[TG-Login] Session injected: DC{dc_id}');
                """
                
                driver.execute_script(script)
                
                # 刷新页面
                self.log(f"🔄 刷新页面...", "INFO")
                driver.refresh()
                time.sleep(3)
                
                # 检查登录状态
                try:
                    qr_elements = driver.find_elements("xpath", "//*[contains(@class, 'qr')]")
                    if qr_elements:
                        self.log(f"⚠️ 首次注入未生效，尝试第二次...", "WARNING")
                        driver.execute_script(script)
                        driver.refresh()
                        time.sleep(3)
                        
                        qr_elements = driver.find_elements("xpath", "//*[contains(@class, 'qr')]")
                        if qr_elements:
                            self.log(f"⚠️ 可能需要手动扫码（session可能已过期）", "WARNING")
                        else:
                            self.log(f"✅ 第二次注入成功！", "SUCCESS")
                    else:
                        self.log(f"✅ {session_name} - Telegram Web已登录！", "SUCCESS")
                        self.log(f"ℹ️  浏览器保持打开，手动关闭即可", "INFO")
                        
                except Exception as check_error:
                    self.log(f"⚠️ 无法检查状态: {check_error}", "WARNING")
                
            except ImportError as ie:
                # Selenium未安装
                self.log(f"❌ 未安装Selenium: pip install selenium", "ERROR")
                
            except Exception as selenium_error:
                # Selenium出错
                self.log(f"❌ Selenium错误: {selenium_error}", "ERROR")
                import traceback
                traceback.print_exc()
            
        except Exception as e:
            self.log(f"❌ Web登录失败: {e}", "ERROR")
            import traceback
            traceback.print_exc()
    
    def select_all_accounts(self):
        """全选"""
        self.selected_accounts = []
        for item in self.account_tree.get_children():
            values = list(self.account_tree.item(item)['values'])
            values[1] = '☑'  # 序号在0，选择框在1
            self.account_tree.item(item, values=values)
            tag_with_prefix = self.account_tree.item(item)['tags'][0]
            session_name = tag_with_prefix.replace('session_', '')  # 去掉前缀
            self.selected_accounts.append(session_name)
        self.update_stats()
    
    def deselect_all_accounts(self):
        """全不选"""
        self.selected_accounts = []
        for item in self.account_tree.get_children():
            values = list(self.account_tree.item(item)['values'])
            values[1] = '☐'  # 序号在0，选择框在1
            self.account_tree.item(item, values=values)
        self.update_stats()
    
    def delete_selected_accounts(self):
        """删除选中的账号"""
        if not self.selected_accounts:
            messagebox.showinfo("提示", "请先选择要删除的账号！")
            return
        
        # 获取选中账号的信息
        selected_infos = []
        for session_name in self.selected_accounts:
            account = next((acc for acc in self.accounts if acc.session_name == session_name), None)
            if account:
                selected_infos.append(f"  - {account.phone} ({account.name}) - {account.status}")
        
        # 确认删除
        msg = f"确定要删除以下 {len(self.selected_accounts)} 个账号吗？\n\n"
        msg += "\n".join(selected_infos[:15])  # 最多显示15个
        if len(self.selected_accounts) > 15:
            msg += f"\n  ... 还有 {len(self.selected_accounts) - 15} 个"
        msg += "\n\n⚠️ 这将删除Session文件，无法恢复！"
        
        if not messagebox.askyesno("确认删除", msg):
            return
        
        # 删除Session文件
        deleted = 0
        for session_name in self.selected_accounts:
            session_file = os.path.join(Config.SESSIONS_DIR, session_name + '.session')
            try:
                if os.path.exists(session_file):
                    os.remove(session_file)
                    deleted += 1
                    account = next((acc for acc in self.accounts if acc.session_name == session_name), None)
                    if account:
                        self.log(f"🗑️ 已删除: {account.phone} ({session_name})", "WARNING")
                    else:
                        self.log(f"🗑️ 已删除: {session_name}", "WARNING")
            except Exception as e:
                self.log(f"❌ 删除失败: {session_name} - {e}", "ERROR")
        
        self.log(f"✅ 已删除 {deleted} 个账号", "SUCCESS")
        
        # 清空选中列表
        self.selected_accounts = []
        
        # 刷新账号列表
        self.refresh_accounts_quick()
    
    def delete_invalid_accounts(self):
        """删除失效/未授权账号"""
        # 找出所有失效账号
        invalid_accounts = [acc for acc in self.accounts if not acc.is_authorized]
        
        if not invalid_accounts:
            messagebox.showinfo("提示", "没有失效账号！")
            return
        
        # 确认删除
        msg = f"发现 {len(invalid_accounts)} 个失效账号：\n\n"
        for acc in invalid_accounts[:10]:  # 最多显示10个
            msg += f"  - {acc.phone} ({acc.name}) - {acc.status}\n"
        if len(invalid_accounts) > 10:
            msg += f"  ... 还有 {len(invalid_accounts) - 10} 个\n"
        msg += f"\n确定要删除这些Session文件吗？"
        
        if not messagebox.askyesno("确认删除", msg):
            return
        
        # 删除Session文件
        deleted = 0
        for acc in invalid_accounts:
            session_file = os.path.join(Config.SESSIONS_DIR, acc.session_name + '.session')
            try:
                if os.path.exists(session_file):
                    os.remove(session_file)
                    deleted += 1
                    self.log(f"🗑️ 已删除: {acc.phone} ({acc.session_name})", "WARNING")
            except Exception as e:
                self.log(f"❌ 删除失败: {acc.session_name} - {e}", "ERROR")
        
        self.log(f"✅ 已删除 {deleted} 个失效账号", "SUCCESS")
        
        # 快速刷新
        self.refresh_accounts_quick()
    
    async def sync_group_data(self):
        """同步群数据（清理joined.json中已退出的群）"""
        self.log("=" * 60, "INFO")
        self.log("🔄 开始同步群数据...", "INFO")
        self.log("=" * 60, "INFO")
        
        # 加载joined.json
        joined_data = DataManager.load_json(Config.JOINED_FILE)
        
        total_accounts = 0
        total_cleaned = 0
        
        for account in self.accounts:
            if not account.is_authorized:
                continue
            
            session_path = os.path.join(Config.SESSIONS_DIR, account.session_name)
            client = TelegramClient(session_path, Config.API_ID, Config.API_HASH)
            
            try:
                await client.connect()
                
                if not await client.is_user_authorized():
                    continue
                
                # 获取真实的群列表
                self.log(f"🔍 [{account.phone}] 正在查询群列表...", "INFO")
                all_dialogs = await client.get_dialogs()
                
                # 统计真实群数量（更新real_group_count）
                real_group_count = sum(1 for d in all_dialogs if d.is_group or d.is_channel)
                account.real_group_count = real_group_count  # 更新账号的实际群数
                
                # 提取所有群组和频道的username和invite link
                real_groups = set()
                for d in all_dialogs:
                    if d.is_group or d.is_channel:
                        # 添加username（如果有）- 安全检查
                        if hasattr(d.entity, 'username') and d.entity.username:
                            real_groups.add(f"@{d.entity.username}")
                            real_groups.add(f"https://t.me/{d.entity.username}")
                        # TODO: 暂时无法获取invite link，只能通过username对比
                
                # 检查joined.json中的群是否还存在
                session_name = account.session_name
                if session_name in joined_data:
                    recorded_groups = joined_data[session_name]
                    
                    # 兼容旧格式
                    if isinstance(recorded_groups, int):
                        self.log(f"⚠️  [{account.phone}] joined.json是旧格式（int），跳过", "WARNING")
                        continue
                    
                    # 检查哪些群已经不在了
                    cleaned_groups = []
                    removed_count = 0
                    
                    for group_link in recorded_groups:
                        # 简单检查：如果群链接包含username，且在real_groups中，保留
                        # 否则，可能已退出
                        found = False
                        for real_group in real_groups:
                            if group_link in real_group or real_group in group_link:
                                found = True
                                break
                        
                        if found:
                            cleaned_groups.append(group_link)
                        else:
                            self.log(f"🗑️  [{account.phone}] 已退出: {group_link}", "WARNING")
                            removed_count += 1
                    
                    # 更新joined.json
                    joined_data[session_name] = cleaned_groups
                    total_cleaned += removed_count
                    total_accounts += 1
                    
                    self.log(f"✅ [{account.phone}] 完成！移除 {removed_count} 个已退出的群", "SUCCESS")
                
                await client.disconnect()
                
            except Exception as e:
                self.log(f"❌ [{account.phone}] 同步失败: {e}", "ERROR")
                try:
                    await client.disconnect()
                except:
                    pass
        
        # 保存更新后的joined.json
        if total_cleaned > 0:
            DataManager.save_json(Config.JOINED_FILE, joined_data)
            self.log(f"💾 已保存更新后的joined.json", "SUCCESS")
        
        self.log("=" * 60, "INFO")
        self.log(f"✅ 同步完成！处理 {total_accounts} 个账号，清理 {total_cleaned} 条无效记录", "SUCCESS")
        self.log("=" * 60, "INFO")
        
        # 刷新账号列表
        self.refresh_accounts_quick()
    
    def update_stats(self):
        """更新统计信息"""
        available = sum(1 for acc in self.accounts if acc.is_authorized)
        selected = len(self.selected_accounts)
        
        # 加载群数量
        groups = []
        if os.path.exists(Config.GROUPS_FILE):
            with open(Config.GROUPS_FILE, 'r', encoding='utf-8') as f:
                groups = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        self.stat_accounts.config(text=f"可用账号: {available}")
        self.stat_selected.config(text=f"已选中: {selected}")
        self.stat_groups.config(text=f"待加群: {len(groups)}")
    
    def import_session(self):
        """导入Session文件"""
        files = filedialog.askopenfilenames(
            title="选择Session文件",
            filetypes=[("Session文件", "*.session"), ("所有文件", "*.*")]
        )
        
        if files:
            for file in files:
                filename = os.path.basename(file)
                dest = os.path.join(Config.SESSIONS_DIR, filename)
                
                try:
                    import shutil
                    shutil.copy(file, dest)
                    self.log(f"✅ 导入成功: {filename}", "SUCCESS")
                except Exception as e:
                    self.log(f"❌ 导入失败: {filename} - {e}", "ERROR")
            
            # 快速刷新列表
            self.refresh_accounts_quick()
    
    def start_join(self):
        """开始加群"""
        if not self.selected_accounts:
            messagebox.showwarning("警告", "请先选择账号！")
            return
        
        self.is_running = True
        self.start_button.config(state=DISABLED)
        self.stop_button.config(state=NORMAL)
        
        # 禁用标签页切换（防止加群时切换导致错误）
        for i in range(self.notebook.index('end')):
            if i != 0:  # 保持主界面可见，禁用其他标签页
                self.notebook.tab(i, state='disabled')
        
        # 在后台线程运行（避免阻塞GUI）
        import threading
        thread = threading.Thread(target=lambda: asyncio.run(self.run_join()), daemon=True)
        thread.start()
    
    def stop_join(self):
        """停止加群"""
        self.is_running = False
        self.start_button.config(state=NORMAL)
        self.stop_button.config(state=DISABLED)
        
        # 恢复标签页切换
        for i in range(self.notebook.index('end')):
            self.notebook.tab(i, state='normal')
        
        self.log("⏸️  已停止", "WARNING")
    
    async def run_join(self):
        """运行加群任务（并发模式）"""
        # 重置计数器
        self.total_success = 0
        self.total_failed = 0
        self.stat_success.config(text="成功: 0")
        self.stat_failed.config(text="失败: 0")
        
        self.log("=" * 60, "INFO")
        self.log(f"🚀 开始加群！使用 {len(self.selected_accounts)} 个账号（并发）", "INFO")
        self.log("=" * 60, "INFO")
        
        # 加载群列表
        if not os.path.exists(Config.GROUPS_FILE):
            self.log("❌ 未找到群列表文件！", "ERROR")
            self.stop_join()
            return
        
        with open(Config.GROUPS_FILE, 'r', encoding='utf-8') as f:
            groups = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        if not groups:
            self.log("❌ 群列表为空！", "ERROR")
            self.stop_join()
            return
        
        self.log(f"📋 待加入群数: {len(groups)}", "INFO")
        self.log(f"🔀 并发模式: {len(self.selected_accounts)} 个账号同时工作", "INFO")
        
        # 不重复模式：使用共享群队列
        if not Config.ALLOW_DUPLICATE:
            self.log("📌 不重复模式：每个群只用一个账号加", "INFO")
            self.remaining_groups = list(groups)  # 共享的待加群队列
            self.group_lock = asyncio.Lock()  # 线程锁
        
        # 为每个账号创建任务
        tasks = []
        for account_idx, session_name in enumerate(self.selected_accounts):
            if Config.ALLOW_DUPLICATE:
                task = self.account_worker(session_name, groups, account_idx)
            else:
                task = self.account_worker_no_duplicate(session_name, account_idx)
            tasks.append(task)
        
        # 并发执行所有账号
        await asyncio.gather(*tasks)
        
        # 完成
        self.log("=" * 60, "INFO")
        self.log(f"✅ 所有账号加群完成！", "SUCCESS")
        self.log("=" * 60, "INFO")
        
        self.stop_join()
        
        # 重新加载账号统计
        self.refresh_accounts_quick()
    
    async def account_worker(self, session_name: str, groups: List[str], account_idx: int):
        """单个账号的加群任务"""
        # 先检查账号是否授权（避免未授权账号等待）
        account = next((acc for acc in self.accounts if acc.session_name == session_name), None)
        if not account or not account.is_authorized:
            self.log(f"❌ [{session_name}] 未授权，跳过", "ERROR")
            self.total_failed += 1
            self.stat_failed.config(text=f"失败: {self.total_failed}")
            return
        
        # 错开启动时间（避免所有账号同时请求）
        initial_delay = random.randint(Config.ACCOUNT_INTERVAL_MIN, Config.ACCOUNT_INTERVAL_MAX) * account_idx
        if initial_delay > 0:
            self.log(f"⏳ [{session_name}] 等待 {initial_delay} 秒后开始...", "INFO")
            await asyncio.sleep(initial_delay)
        
        self.log(f"🚀 [{session_name}] 开始加群！", "INFO")
        
        success = 0
        failed = 0
        skipped = 0
        
        # 加载已加入的群（所有账号）
        joined_all = DataManager.load_json(Config.JOINED_FILE)
        
        for idx, link in enumerate(groups):
            if not self.is_running:
                self.log(f"⏸️  [{session_name}] 已停止", "WARNING")
                break
            
            # 如果是不重复模式，检查是否已被其他账号加入
            if not Config.ALLOW_DUPLICATE:
                already_joined_by_others = False
                for other_session, other_groups in joined_all.items():
                    # 兼容性检查：other_groups可能是int（旧格式）或list（新格式）
                    if isinstance(other_groups, int):
                        continue  # 旧格式，跳过
                    
                    if other_session != session_name and link in other_groups:
                        # 只计数，不打印日志（减少刷屏）
                        skipped += 1
                        already_joined_by_others = True
                        break
                
                if already_joined_by_others:
                    continue
            
            # 加入群
            result = await self.join_group(session_name, link)
            
            # 检查账号是否死了（未授权）
            if result == 'UNAUTHORIZED':
                self.log(f"❌ [{session_name}] 账号未授权，停止该账号的加群任务", "ERROR")
                break  # 停止循环，不再尝试后续群
            
            if result:
                success += 1
                # 重新加载joined.json（可能被其他账号更新了）
                joined_all = DataManager.load_json(Config.JOINED_FILE)
            else:
                failed += 1
            
            # 智能间隔（避免被限流）
            if idx < len(groups) - 1:  # 不是最后一个群
                interval = random.randint(Config.INTERVAL_MIN, Config.INTERVAL_MAX)
                self.log(f"⏰ [{session_name}] 等待 {interval} 秒...", "INFO")
                await asyncio.sleep(interval)
        
        summary = f"✅ [{session_name}] 完成！成功: {success}, 失败: {failed}"
        if not Config.ALLOW_DUPLICATE and skipped > 0:
            summary += f", 跳过: {skipped}"
        self.log(summary, "SUCCESS")
    
    async def account_worker_no_duplicate(self, session_name: str, account_idx: int):
        """不重复模式的账号worker（从共享群池中取群）"""
        # 先检查账号是否授权
        account = next((acc for acc in self.accounts if acc.session_name == session_name), None)
        if not account or not account.is_authorized:
            self.log(f"❌ [{session_name}] 未授权，跳过", "ERROR")
            self.total_failed += 1
            self.stat_failed.config(text=f"失败: {self.total_failed}")
            return
        
        # 错开启动时间
        initial_delay = random.randint(Config.ACCOUNT_INTERVAL_MIN, Config.ACCOUNT_INTERVAL_MAX) * account_idx
        if initial_delay > 0:
            self.log(f"⏳ [{session_name}] 等待 {initial_delay} 秒后开始...", "INFO")
            await asyncio.sleep(initial_delay)
        
        self.log(f"🚀 [{session_name}] 开始加群！", "INFO")
        
        success = 0
        failed = 0
        
        while True:
            if not self.is_running:
                self.log(f"⏸️  [{session_name}] 已停止", "WARNING")
                break
            
            # 从共享群池中取一个群（线程安全）
            async with self.group_lock:
                if not self.remaining_groups:
                    # 群加完了！
                    self.log(f"✅ [{session_name}] 群池已空，停止", "SUCCESS")
                    break
                
                link = self.remaining_groups[0]  # 取第一个群
            
            # 加入群
            result = await self.join_group(session_name, link)
            
            # 检查账号是否死了
            if result == 'UNAUTHORIZED':
                self.log(f"❌ [{session_name}] 账号未授权，停止该账号的加群任务", "ERROR")
                break
            
            # 检查是否FloodWait过长
            if result == 'FLOODWAIT':
                self.log(f"⚠️ [{session_name}] FloodWait时间过长，停止该账号", "WARNING")
                break
            
            # 根据结果处理
            if result:
                success += 1
                # 成功 → 从群池删除这个群
                async with self.group_lock:
                    if link in self.remaining_groups:
                        self.remaining_groups.remove(link)
                        self.log(f"📌 [{session_name}] 群已加入，从池中移除: {link}", "INFO")
            else:
                failed += 1
                # 失败 → 也从群池删除（避免其他账号重复失败）
                async with self.group_lock:
                    if link in self.remaining_groups:
                        self.remaining_groups.remove(link)
                        self.log(f"⚠️ [{session_name}] 加群失败，从池中移除: {link}", "WARNING")
            
            # 检查群池是否为空
            async with self.group_lock:
                if not self.remaining_groups:
                    self.log(f"✅ [{session_name}] 所有群已处理完毕", "SUCCESS")
                    break
            
            # 智能间隔
            interval = random.randint(Config.INTERVAL_MIN, Config.INTERVAL_MAX)
            self.log(f"⏰ [{session_name}] 等待 {interval} 秒...", "INFO")
            await asyncio.sleep(interval)
        
        self.log(f"✅ [{session_name}] 完成！成功: {success}, 失败: {failed}", "SUCCESS")
    
    async def join_group(self, session_name: str, link: str) -> bool:
        """单个账号加入群"""
        # 类型检查
        if not isinstance(session_name, str):
            self.log(f"❌ 错误: session_name类型错误 ({type(session_name)}): {session_name}", "ERROR")
            self.remove_group_link(link)  # 删除失效链接
            return False
        
        session_path = os.path.join(Config.SESSIONS_DIR, session_name)
        client = TelegramClient(session_path, Config.API_ID, Config.API_HASH)
        
        try:
            await client.connect()
            
            if not await client.is_user_authorized():
                self.log(f"❌ [{session_name}] 未授权（死号），停止使用该账号", "ERROR")
                # 标记账号为未授权状态
                account = next((acc for acc in self.accounts if acc.session_name == session_name), None)
                if account:
                    account.is_authorized = False
                    account.status = '❌ 未授权'
                return 'UNAUTHORIZED'  # 返回特殊值，通知worker停止
            
            # 解析链接
            parsed = GroupLinkParser.parse_link(link)
            if not parsed:
                self.log(f"⚠️  [{session_name}] 无法解析: {link}", "WARNING")
                self.remove_group_link(link)  # 删除失效链接
                return False
            
            # 尝试加入
            if parsed['type'] == 'invite':
                await client(ImportChatInviteRequest(parsed['hash']))
            else:
                await client(JoinChannelRequest(parsed['username']))
            
            # 成功
            DataManager.mark_joined(session_name, link)
            self.log(f"✅ [{session_name}] 成功加入: {link}", "SUCCESS")
            self.remove_group_link(link)  # 删除已加入的群链接
            self.total_success += 1
            self.stat_success.config(text=f"成功: {self.total_success}")
            return True
        
        except errors.UserAlreadyParticipantError:
            DataManager.mark_joined(session_name, link)
            self.log(f"ℹ️  [{session_name}] 已在群里: {link}", "INFO")
            self.remove_group_link(link)  # 删除已加入的群链接
            self.total_success += 1
            self.stat_success.config(text=f"成功: {self.total_success}")
            return True
        
        except errors.FloodWaitError as flood:
            # FloodWait错误：Telegram要求等待
            wait_seconds = flood.seconds
            self.log(f"⚠️ [{session_name}] FloodWait: 需等待 {wait_seconds} 秒", "WARNING")
            
            if wait_seconds <= 120:  # 2分钟以内，自动等待
                self.log(f"⏳ [{session_name}] 自动等待 {wait_seconds} 秒后重试...", "INFO")
                await asyncio.sleep(wait_seconds + 5)  # 多等5秒保险
                
                # 重试加群
                try:
                    if parsed['type'] == 'invite':
                        await client(ImportChatInviteRequest(parsed['hash']))
                    else:
                        await client(JoinChannelRequest(parsed['username']))
                    
                    DataManager.mark_joined(session_name, link)
                    self.log(f"✅ [{session_name}] 重试成功: {link}", "SUCCESS")
                    self.remove_group_link(link)
                    self.total_success += 1
                    self.stat_success.config(text=f"成功: {self.total_success}")
                    return True
                except Exception as retry_err:
                    self.log(f"❌ [{session_name}] 重试失败: {link} - {retry_err}", "ERROR")
                    self.total_failed += 1
                    self.stat_failed.config(text=f"失败: {self.total_failed}")
                    return False
            else:  # 超过2分钟，跳过这个账号
                self.log(f"❌ [{session_name}] FloodWait时间过长({wait_seconds}秒)，跳过该账号", "ERROR")
                self.total_failed += 1
                self.stat_failed.config(text=f"失败: {self.total_failed}")
                return 'FLOODWAIT'  # 返回特殊值，通知worker停止该账号
        
        except Exception as e:
            error_msg = str(e)
            if 'successfully requested to join' in error_msg.lower():
                DataManager.mark_joined(session_name, link)
                self.log(f"✅ [{session_name}] 已申请入群，待审核: {link} ⏳", "SUCCESS")
                self.remove_group_link(link)  # 删除已申请的群链接
                self.total_success += 1
                self.stat_success.config(text=f"成功: {self.total_success}")
                return True
            
            # 判断是否是永久失败（删除链接）
            if any(keyword in error_msg.lower() for keyword in ['not found', 'invalid', 'private', 'banned']):
                self.log(f"❌ [{session_name}] 失败（永久）: {link} - {e}", "ERROR")
                self.remove_group_link(link)  # 删除失效链接
            else:
                self.log(f"❌ [{session_name}] 失败（临时）: {link} - {e}", "ERROR")
            
            self.total_failed += 1
            self.stat_failed.config(text=f"失败: {self.total_failed}")
            return False
        
        finally:
            await client.disconnect()
    
    def remove_group_link(self, link: str):
        """从groups.txt删除群链接"""
        try:
            if not os.path.exists(Config.GROUPS_FILE):
                return
            
            with open(Config.GROUPS_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 过滤掉要删除的链接
            new_lines = [line for line in lines if line.strip() != link.strip()]
            
            with open(Config.GROUPS_FILE, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            
            # 更新GUI中的群链接文本框（如果存在）
            if hasattr(self, 'groups_text'):
                self.groups_text.delete('1.0', END)
                self.groups_text.insert('1.0', ''.join(new_lines))
                self.update_groups_count()
        
        except Exception as e:
            print(f"删除群链接失败: {e}")
    
    def setup_broadcast_tab(self, parent):
        """群发消息标签页"""
        # 创建可滚动的Canvas
        canvas = Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 绑定鼠标滚轮
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # 使用scrollable_frame作为父容器
        parent_container = scrollable_frame
        
        # 消息内容区
        content_frame = LabelFrame(parent_container, text="📝 消息内容", 
                                   font=self.font_menu, padx=10, pady=10)
        content_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        Label(content_frame, text="消息文本:", font=self.font_label).grid(row=0, column=0, sticky=W, pady=5)
        self.broadcast_text = Text(content_frame, height=6, width=60, font=self.font_label)
        self.broadcast_text.grid(row=1, column=0, columnspan=2, sticky=W+E, padx=5, pady=5)
        
        # 变量支持
        self.broadcast_use_variables_var = BooleanVar(value=True)
        Checkbutton(content_frame, text="支持变量 (群名:{group_name}, 序号:{index}, 时间:{time})", 
                   variable=self.broadcast_use_variables_var, font=self.font_label).grid(row=2, column=0, sticky=W, pady=2)
        
        # 随机改写
        self.broadcast_random_rewrite_var = BooleanVar(value=False)
        Checkbutton(content_frame, text="随机改写（每条消息轻微变化）", 
                   variable=self.broadcast_random_rewrite_var, font=self.font_label).grid(row=3, column=0, sticky=W, pady=2)
        
        # 图片选择
        Label(content_frame, text="图片（可选）:", font=self.font_label).grid(row=4, column=0, sticky=W, pady=5)
        self.broadcast_image_path = StringVar()
        image_frame = Frame(content_frame)
        image_frame.grid(row=5, column=0, sticky=W+E, pady=5)
        Entry(image_frame, textvariable=self.broadcast_image_path, width=40, font=self.font_label).pack(side=LEFT, padx=2)
        Button(image_frame, text="选择图片", command=self.select_broadcast_image, 
               font=("Arial", 10, "bold"), bg="#2196F3", fg="white").pack(side=LEFT, padx=2)
        Button(image_frame, text="清除", command=lambda: self.broadcast_image_path.set(""), 
               font=("Arial", 10, "bold"), bg="#9E9E9E", fg="white").pack(side=LEFT, padx=2)
        
        # 发送目标
        target_frame = LabelFrame(parent_container, text="🎯 发送目标", 
                                 font=self.font_menu, padx=10, pady=10)
        target_frame.pack(fill=X, padx=10, pady=5)
        
        self.broadcast_target_var = StringVar(value="file")
        Radiobutton(target_frame, text="所有已加入的群组", variable=self.broadcast_target_var, 
                   value="joined", font=self.font_label).grid(row=0, column=0, sticky=W, pady=2)
        Radiobutton(target_frame, text="群列表文件（groups.txt）", variable=self.broadcast_target_var, 
                   value="file", font=self.font_label).grid(row=1, column=0, sticky=W, pady=2)
        Radiobutton(target_frame, text="选中的群组（手动勾选）", variable=self.broadcast_target_var, 
                   value="selected", font=self.font_label).grid(row=2, column=0, sticky=W, pady=2)
        
        # 群组列表区（用于手动勾选）
        groups_list_frame = LabelFrame(parent_container, text="📋 群组列表（手动勾选模式）", 
                                      font=self.font_menu, padx=10, pady=10)
        groups_list_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # 创建群组列表Treeview
        columns = ('选择', '序号', '群组名称', '类型')
        self.broadcast_groups_tree = ttk.Treeview(groups_list_frame, columns=columns, 
                                                 show='headings', height=6)
        
        self.broadcast_groups_tree.column('选择', width=50, anchor=CENTER)
        self.broadcast_groups_tree.column('序号', width=50, anchor=CENTER)
        self.broadcast_groups_tree.column('群组名称', width=250, anchor=W)
        self.broadcast_groups_tree.column('类型', width=80, anchor=CENTER)
        
        for col in columns:
            self.broadcast_groups_tree.heading(col, text=col)
        
        groups_scrollbar = ttk.Scrollbar(groups_list_frame, orient=VERTICAL, 
                                        command=self.broadcast_groups_tree.yview)
        self.broadcast_groups_tree.configure(yscrollcommand=groups_scrollbar.set)
        
        self.broadcast_groups_tree.pack(side=LEFT, fill=BOTH, expand=True)
        groups_scrollbar.pack(side=RIGHT, fill=Y)
        
        # 双击切换选择
        self.broadcast_groups_tree.bind('<Double-1>', self.toggle_broadcast_group_selection)
        
        # 群组操作按钮
        groups_btn_frame = Frame(parent_container)
        groups_btn_frame.pack(fill=X, padx=10, pady=5)
        
        Button(groups_btn_frame, text="🔄 加载已加入的群组", font=("Arial", 10, "bold"),
               command=lambda: threading.Thread(target=lambda: asyncio.run(self.load_joined_groups()), daemon=True).start(),
               bg="#2196F3", fg="white", width=18).pack(side=LEFT, padx=2)
        
        Button(groups_btn_frame, text="✅ 全选", font=("Arial", 10, "bold"),
               command=self.select_all_broadcast_groups,
               bg="#FF9800", fg="white", width=8).pack(side=LEFT, padx=2)
        
        Button(groups_btn_frame, text="❌ 全不选", font=("Arial", 10, "bold"),
               command=self.deselect_all_broadcast_groups,
               bg="#9E9E9E", fg="white", width=9).pack(side=LEFT, padx=2)
        
        # 发送配置
        config_frame = LabelFrame(parent_container, text="⚙️ 发送配置", 
                                 font=self.font_menu, padx=10, pady=10)
        config_frame.pack(fill=X, padx=10, pady=5)
        
        Label(config_frame, text="间隔时间(秒):", font=self.font_label).grid(row=0, column=0, sticky=W, pady=5)
        self.broadcast_interval_min_var = IntVar(value=30)
        Entry(config_frame, textvariable=self.broadcast_interval_min_var, font=self.font_label, width=10).grid(row=0, column=1, pady=5)
        Label(config_frame, text="-", font=self.font_label).grid(row=0, column=2, pady=5)
        self.broadcast_interval_max_var = IntVar(value=90)
        Entry(config_frame, textvariable=self.broadcast_interval_max_var, font=self.font_label, width=10).grid(row=0, column=3, pady=5)
        
        Label(config_frame, text="每日限额(条/账号):", font=self.font_label).grid(row=1, column=0, sticky=W, pady=5)
        self.broadcast_daily_limit_var = IntVar(value=100)
        Entry(config_frame, textvariable=self.broadcast_daily_limit_var, font=self.font_label, width=10).grid(row=1, column=1, pady=5)
        
        Label(config_frame, text="批次大小:", font=self.font_label).grid(row=2, column=0, sticky=W, pady=5)
        self.broadcast_batch_size_var = IntVar(value=10)
        Entry(config_frame, textvariable=self.broadcast_batch_size_var, font=self.font_label, width=10).grid(row=2, column=1, pady=5)
        
        Label(config_frame, text="批次休息(秒):", font=self.font_label).grid(row=3, column=0, sticky=W, pady=5)
        self.broadcast_batch_rest_min_var = IntVar(value=300)
        Entry(config_frame, textvariable=self.broadcast_batch_rest_min_var, font=self.font_label, width=10).grid(row=3, column=1, pady=5)
        Label(config_frame, text="-", font=self.font_label).grid(row=3, column=2, pady=5)
        self.broadcast_batch_rest_max_var = IntVar(value=600)
        Entry(config_frame, textvariable=self.broadcast_batch_rest_max_var, font=self.font_label, width=10).grid(row=3, column=3, pady=5)
        
        Label(config_frame, text="并发线程:", font=self.font_label).grid(row=4, column=0, sticky=W, pady=5)
        self.broadcast_threads_var = IntVar(value=10)
        Entry(config_frame, textvariable=self.broadcast_threads_var, font=self.font_label, width=10).grid(row=4, column=1, pady=5)
        
        # 统计信息
        stats_info_frame = LabelFrame(parent_container, text="📊 发送统计", 
                                     font=self.font_menu, padx=10, pady=10)
        stats_info_frame.pack(fill=X, padx=10, pady=5)
        
        self.broadcast_stat_sent = Label(stats_info_frame, text="已发送: 0/0", font=self.font_label, fg="blue")
        self.broadcast_stat_sent.pack(side=LEFT, padx=10)
        
        self.broadcast_stat_success = Label(stats_info_frame, text="成功: 0", font=self.font_label, fg="green")
        self.broadcast_stat_success.pack(side=LEFT, padx=10)
        
        self.broadcast_stat_failed = Label(stats_info_frame, text="失败: 0", font=self.font_label, fg="red")
        self.broadcast_stat_failed.pack(side=LEFT, padx=10)
        
        # 操作按钮
        btn_frame = Frame(parent_container)
        btn_frame.pack(fill=X, padx=10, pady=10)
        
        Button(btn_frame, text="▶️ 开始群发", font=self.font_button,
               command=lambda: threading.Thread(target=lambda: asyncio.run(self.start_broadcast()), daemon=True).start(),
               bg="#4CAF50", fg="white", width=12, height=1).pack(side=LEFT, padx=5)
        
        Button(btn_frame, text="⏹️ 停止", font=self.font_button,
               command=self.stop_broadcast,
               bg="#F44336", fg="white", width=12, height=1).pack(side=LEFT, padx=5)
    
    def select_broadcast_image(self):
        """选择群发图片"""
        from tkinter import filedialog
        filepath = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.gif *.bmp"), ("所有文件", "*.*")]
        )
        if filepath:
            self.broadcast_image_path.set(filepath)
            self.log(f"✅ 已选择图片: {filepath}", "SUCCESS")
    
    async def start_broadcast(self):
        """开始群发"""
        # 获取消息内容
        message = self.broadcast_text.get('1.0', END).strip()
        if not message and not self.broadcast_image_path.get():
            messagebox.showerror("错误", "请输入消息内容或选择图片！")
            return
        
        # 检查选中的账号
        if not self.selected_accounts:
            messagebox.showerror("错误", "请先选择要使用的账号！")
            return
        
        self.log("=" * 60, "INFO")
        self.log("📤 开始群发消息...", "INFO")
        self.log("=" * 60, "INFO")
        
        # 重置统计
        self.broadcast_total_sent = 0
        self.broadcast_total_success = 0
        self.broadcast_total_failed = 0
        self.is_broadcasting = True
        
        # 获取目标群组列表
        target_mode = self.broadcast_target_var.get()
        target_groups = []
        
        if target_mode == "joined":
            # 所有已加入的群组
            if not self.broadcast_groups:
                messagebox.showerror("错误", "请先点击'加载已加入的群组'！")
                return
            
            self.log(f"🎯 目标: 所有已加入的群组，共 {len(self.broadcast_groups)} 个", "INFO")
            target_groups = self.broadcast_groups
            
        elif target_mode == "selected":
            # 选中的群组
            if not self.selected_broadcast_groups:
                messagebox.showerror("错误", "请先勾选要发送的群组！")
                return
            
            selected_groups = [self.broadcast_groups[idx] for idx in self.selected_broadcast_groups]
            self.log(f"🎯 目标: 选中的群组，共 {len(selected_groups)} 个", "INFO")
            target_groups = selected_groups
            
        elif target_mode == "file":
            # 从groups.txt
            if not os.path.exists(Config.GROUPS_FILE):
                messagebox.showerror("错误", f"未找到群列表文件: {Config.GROUPS_FILE}")
                return
            
            with open(Config.GROUPS_FILE, 'r', encoding='utf-8') as f:
                groups = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            if not groups:
                messagebox.showerror("错误", "群列表为空！")
                return
            
            self.log(f"🎯 目标: 群列表文件，共 {len(groups)} 个群", "INFO")
            
            # 转换为统一格式
            target_groups = [{'type': 'link', 'link': link} for link in groups]
        
        # 开始群发
        await self.broadcast_to_groups_new(target_groups, message)
        
        self.log("=" * 60, "INFO")
        self.log("✅ 群发完成！", "SUCCESS")
        self.log("=" * 60, "INFO")
    
    async def broadcast_to_groups_new(self, target_groups, message):
        """新版群发（支持多账号并发）"""
        # 检查是否有多个账号
        if len(self.selected_accounts) > 1:
            self.log(f"🔀 多账号并发模式: {len(self.selected_accounts)} 个账号", "INFO")
            # 分配群组给账号
            groups_per_account = len(target_groups) // len(self.selected_accounts)
            
            tasks = []
            for idx, session_name in enumerate(self.selected_accounts):
                start_idx = idx * groups_per_account
                end_idx = start_idx + groups_per_account if idx < len(self.selected_accounts) - 1 else len(target_groups)
                account_groups = target_groups[start_idx:end_idx]
                
                if account_groups:
                    self.log(f"📋 [{session_name}] 负责 {len(account_groups)} 个群组", "INFO")
                    task = self.broadcast_worker(session_name, account_groups, message, idx)
                    tasks.append(task)
            
            # 并发执行
            await asyncio.gather(*tasks)
        else:
            # 单账号模式
            session_name = self.selected_accounts[0]
            self.log(f"👤 单账号模式: {session_name}", "INFO")
            await self.broadcast_worker(session_name, target_groups, message, 0)
    
    async def broadcast_worker(self, session_name, target_groups, message, worker_idx):
        """单个账号的群发worker"""
        # 错开启动时间
        initial_delay = worker_idx * random.randint(5, 15)
        if initial_delay > 0:
            self.log(f"⏳ [{session_name}] 等待 {initial_delay} 秒后开始...", "INFO")
            await asyncio.sleep(initial_delay)
        
        session_path = os.path.join(Config.SESSIONS_DIR, session_name)
        client = TelegramClient(session_path, Config.API_ID, Config.API_HASH)
        
        try:
            await client.connect()
            
            if not await client.is_user_authorized():
                self.log(f"❌ [{session_name}] 未授权", "ERROR")
                return
            
            self.log(f"🚀 [{session_name}] 开始群发！", "INFO")
            
            for idx, group_info in enumerate(target_groups, start=1):
                if not self.is_broadcasting:
                    self.log(f"⏹️ [{session_name}] 已停止", "WARNING")
                    break
                
                # 构造消息
                msg = self.prepare_message(message, idx, group_info)
                
                # 发送
                success = await self.send_to_group_new(client, session_name, group_info, msg)
                
                if success:
                    self.broadcast_total_success += 1
                    self.broadcast_stat_success.config(text=f"成功: {self.broadcast_total_success}")
                else:
                    self.broadcast_total_failed += 1
                    self.broadcast_stat_failed.config(text=f"失败: {self.broadcast_total_failed}")
                
                self.broadcast_total_sent += 1
                self.broadcast_stat_sent.config(text=f"已发送: {self.broadcast_total_sent}/{len(target_groups) * len(self.selected_accounts)}")
                
                # 间隔
                if idx < len(target_groups):
                    interval = random.randint(
                        self.broadcast_interval_min_var.get(),
                        self.broadcast_interval_max_var.get()
                    )
                    self.log(f"⏰ [{session_name}] 等待 {interval} 秒...", "INFO")
                    await asyncio.sleep(interval)
            
            self.log(f"✅ [{session_name}] 完成！", "SUCCESS")
        
        except Exception as e:
            self.log(f"❌ [{session_name}] 错误: {e}", "ERROR")
        
        finally:
            await client.disconnect()
    
    def prepare_message(self, message, idx, group_info):
        """准备消息（变量替换+随机改写）"""
        msg = message
        
        # 变量替换
        if self.broadcast_use_variables_var.get():
            msg = msg.replace("{index}", str(idx))
            msg = msg.replace("{time}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            
            # 获取群组名称
            if 'name' in group_info:
                group_name = group_info['name']
            elif 'link' in group_info:
                group_name = group_info['link'].split('/')[-1]
            else:
                group_name = "未知"
            
            msg = msg.replace("{group_name}", group_name)
        
        # 随机改写
        if self.broadcast_random_rewrite_var.get():
            import random
            emojis = ['😊', '👋', '✨', '🌟', '💫', '🎉', '🔥', '💪']
            msg += f" {random.choice(emojis)}"
        
        return msg
    
    async def send_to_group_new(self, client, session_name, group_info, message):
        """发送消息到群组（新版，支持FloodWait）"""
        try:
            # 确定发送目标
            if 'entity' in group_info:
                # 直接使用entity
                target = group_info['entity']
                group_name = group_info.get('name', '未知')
            elif 'link' in group_info:
                # 解析链接
                parsed = GroupLinkParser.parse_link(group_info['link'])
                if not parsed:
                    self.log(f"⚠️ [{session_name}] 无法解析: {group_info['link']}", "WARNING")
                    return False
                
                target = parsed['username'] if parsed['type'] == 'username' else parsed['hash']
                group_name = group_info['link']
            else:
                self.log(f"⚠️ [{session_name}] 无效的群组信息", "WARNING")
                return False
            
            # 发送消息
            if self.broadcast_image_path.get():
                # 有图片
                await client.send_message(target, message, file=self.broadcast_image_path.get())
            else:
                # 纯文本
                await client.send_message(target, message)
            
            self.log(f"✅ [{session_name}] 发送成功: {group_name}", "SUCCESS")
            return True
        
        except errors.FloodWaitError as flood:
            # FloodWait处理
            wait_seconds = flood.seconds
            self.log(f"⚠️ [{session_name}] FloodWait: 需等待 {wait_seconds} 秒", "WARNING")
            
            if wait_seconds <= 120:
                # 自动等待
                self.log(f"⏳ [{session_name}] 自动等待 {wait_seconds} 秒后重试...", "INFO")
                await asyncio.sleep(wait_seconds + 5)
                
                # 重试
                try:
                    if self.broadcast_image_path.get():
                        await client.send_message(target, message, file=self.broadcast_image_path.get())
                    else:
                        await client.send_message(target, message)
                    
                    self.log(f"✅ [{session_name}] 重试成功: {group_name}", "SUCCESS")
                    return True
                except:
                    self.log(f"❌ [{session_name}] 重试失败: {group_name}", "ERROR")
                    return False
            else:
                # 时间太长，跳过
                self.log(f"❌ [{session_name}] FloodWait时间过长，跳过", "ERROR")
                return False
        
        except Exception as e:
            group_name = group_info.get('name', group_info.get('link', '未知'))
            self.log(f"❌ [{session_name}] 发送失败: {group_name} - {e}", "ERROR")
            return False
    
    async def broadcast_to_groups(self, groups, message):
        """向群组列表群发消息"""
        for idx, group_link in enumerate(groups, start=1):
            if not self.is_broadcasting:
                self.log("⏹️ 群发已停止", "WARNING")
                break
            
            # 替换变量
            if self.broadcast_use_variables_var.get():
                msg = message.replace("{index}", str(idx))
                msg = msg.replace("{time}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                msg = msg.replace("{group_name}", group_link.split('/')[-1])  # 临时用链接末尾作为群名
            else:
                msg = message
            
            # 随机改写
            if self.broadcast_random_rewrite_var.get():
                import random
                emojis = ['😊', '👋', '✨', '🌟', '💫', '🎉', '🔥', '💪']
                msg += f" {random.choice(emojis)}"
            
            # 发送
            success = await self.send_message_to_group(group_link, msg)
            
            if success:
                self.broadcast_total_success += 1
                self.broadcast_stat_success.config(text=f"成功: {self.broadcast_total_success}")
            else:
                self.broadcast_total_failed += 1
                self.broadcast_stat_failed.config(text=f"失败: {self.broadcast_total_failed}")
            
            self.broadcast_total_sent += 1
            self.broadcast_stat_sent.config(text=f"已发送: {self.broadcast_total_sent}/{len(groups)}")
            
            # 间隔
            if idx < len(groups):
                interval = random.randint(
                    self.broadcast_interval_min_var.get(),
                    self.broadcast_interval_max_var.get()
                )
                self.log(f"⏰ 等待 {interval} 秒...", "INFO")
                await asyncio.sleep(interval)
    
    async def send_message_to_group(self, group_link, message):
        """向单个群组发送消息"""
        # 使用第一个选中的账号（简化版，后续可改为轮换）
        if not self.selected_accounts:
            return False
        
        session_name = self.selected_accounts[0]
        session_path = os.path.join(Config.SESSIONS_DIR, session_name)
        client = TelegramClient(session_path, Config.API_ID, Config.API_HASH)
        
        try:
            await client.connect()
            
            if not await client.is_user_authorized():
                self.log(f"❌ [{session_name}] 未授权", "ERROR")
                return False
            
            # 解析群链接
            parsed = GroupLinkParser.parse_link(group_link)
            if not parsed:
                self.log(f"⚠️ 无法解析: {group_link}", "WARNING")
                return False
            
            # 发送消息
            if self.broadcast_image_path.get():
                # 有图片
                await client.send_message(
                    parsed['username'] if parsed['type'] == 'username' else parsed['hash'],
                    message,
                    file=self.broadcast_image_path.get()
                )
            else:
                # 纯文本
                await client.send_message(
                    parsed['username'] if parsed['type'] == 'username' else parsed['hash'],
                    message
                )
            
            self.log(f"✅ 发送成功: {group_link}", "SUCCESS")
            return True
        
        except Exception as e:
            self.log(f"❌ 发送失败: {group_link} - {e}", "ERROR")
            return False
        
        finally:
            await client.disconnect()
    
    def stop_broadcast(self):
        """停止群发"""
        self.is_broadcasting = False
        self.log("⏹️ 正在停止群发...", "WARNING")
    
    async def load_joined_groups(self):
        """加载已加入的群组"""
        self.log("=" * 60, "INFO")
        self.log("🔄 开始加载已加入的群组...", "INFO")
        self.log("=" * 60, "INFO")
        
        if not self.selected_accounts:
            messagebox.showerror("错误", "请先选择账号！")
            return
        
        # 清空列表
        for item in self.broadcast_groups_tree.get_children():
            self.broadcast_groups_tree.delete(item)
        
        self.broadcast_groups = []
        
        # 使用第一个选中的账号
        session_name = self.selected_accounts[0]
        session_path = os.path.join(Config.SESSIONS_DIR, session_name)
        client = TelegramClient(session_path, Config.API_ID, Config.API_HASH)
        
        try:
            await client.connect()
            
            if not await client.is_user_authorized():
                self.log(f"❌ [{session_name}] 未授权", "ERROR")
                return
            
            self.log(f"🔍 [{session_name}] 正在查询群组列表...", "INFO")
            all_dialogs = await client.get_dialogs()
            
            # 过滤出群组和频道
            idx = 0
            for d in all_dialogs:
                if d.is_group or d.is_channel:
                    idx += 1
                    group_type = "频道" if d.is_channel else "群组"
                    group_name = d.name or "未知"
                    group_username = d.entity.username if hasattr(d.entity, 'username') and d.entity.username else None
                    
                    # 保存群组信息
                    group_info = {
                        'name': group_name,
                        'type': group_type,
                        'username': group_username,
                        'entity': d.entity
                    }
                    self.broadcast_groups.append(group_info)
                    
                    # 添加到列表
                    values = ('☐', str(idx), group_name, group_type)
                    self.broadcast_groups_tree.insert('', END, values=values, tags=(f'group_{idx}',))
            
            self.log(f"✅ 已加载 {idx} 个群组/频道", "SUCCESS")
        
        except Exception as e:
            self.log(f"❌ 加载失败: {e}", "ERROR")
        
        finally:
            await client.disconnect()
    
    def toggle_broadcast_group_selection(self, event):
        """切换群组选择状态"""
        item = self.broadcast_groups_tree.identify_row(event.y)
        if not item:
            return
        
        # 获取tag（group_idx）
        tag_with_prefix = self.broadcast_groups_tree.item(item)['tags'][0]
        group_idx = int(tag_with_prefix.replace('group_', '')) - 1  # 转为0-based索引
        
        # 切换选择状态
        current_values = list(self.broadcast_groups_tree.item(item)['values'])
        if current_values[0] == '☐':
            current_values[0] = '☑'
            if group_idx not in self.selected_broadcast_groups:
                self.selected_broadcast_groups.append(group_idx)
        else:
            current_values[0] = '☐'
            if group_idx in self.selected_broadcast_groups:
                self.selected_broadcast_groups.remove(group_idx)
        
        self.broadcast_groups_tree.item(item, values=current_values)
    
    def select_all_broadcast_groups(self):
        """全选群组"""
        self.selected_broadcast_groups = []
        for idx, item in enumerate(self.broadcast_groups_tree.get_children()):
            values = list(self.broadcast_groups_tree.item(item)['values'])
            values[0] = '☑'
            self.broadcast_groups_tree.item(item, values=values)
            self.selected_broadcast_groups.append(idx)
        self.log(f"✅ 已全选 {len(self.selected_broadcast_groups)} 个群组", "INFO")
    
    def deselect_all_broadcast_groups(self):
        """全不选群组"""
        self.selected_broadcast_groups = []
        for item in self.broadcast_groups_tree.get_children():
            values = list(self.broadcast_groups_tree.item(item)['values'])
            values[0] = '☐'
            self.broadcast_groups_tree.item(item, values=values)
        self.log("✅ 已取消全选", "INFO")
    
    def log(self, message: str, level: str = "INFO"):
        """输出日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(END, f"[{timestamp}] {message}\n", level)
        self.log_text.see(END)
        self.root.update()

# ===== 主入口 =====
def main():
    root = Tk()
    app = SmartJoinGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()
