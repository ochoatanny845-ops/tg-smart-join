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
        self.joined_count = 0
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
                self.status = '✅ 正常'
                self.is_authorized = True
                print(f"[DEBUG] {self.session_name}: 授权成功 - {self.phone} ({self.name})")
            else:
                self.status = '❌ 未授权'
                self.is_authorized = False
                print(f"[DEBUG] {self.session_name}: 未授权")
            
            # 加载已加入群数
            self.joined_count = DataManager.get_joined_count(self.session_name)
            
        except Exception as e:
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
    
    def setup_main_tab(self, parent):
        """主界面标签页"""
        
        # 顶部：账号列表
        account_frame = LabelFrame(parent, text="📱 账号列表", 
                                   font=self.font_menu, padx=10, pady=10)
        account_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # 账号表格
        columns = ('序号', '选择', '手机号', '名字', '状态', '已加群数')
        self.account_tree = ttk.Treeview(account_frame, columns=columns, 
                                        show='headings', height=8)
        
        # 列宽
        self.account_tree.column('序号', width=50, anchor=CENTER)
        self.account_tree.column('选择', width=50, anchor=CENTER)
        self.account_tree.column('手机号', width=150, anchor=CENTER)
        self.account_tree.column('名字', width=120, anchor=CENTER)
        self.account_tree.column('状态', width=150, anchor=CENTER)
        self.account_tree.column('已加群数', width=120, anchor=CENTER)
        
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
        
        # 账号操作按钮
        account_btn_frame = Frame(parent)
        account_btn_frame.pack(fill=X, padx=10, pady=5)
        
        Button(account_btn_frame, text="🔄 刷新列表", font=self.font_button, 
               command=self.refresh_accounts_quick, 
               bg="#2196F3", fg="white", width=12).pack(side=LEFT, padx=5)
        
        Button(account_btn_frame, text="🔍 检查状态", font=self.font_button, 
               command=lambda: threading.Thread(target=lambda: asyncio.run(self.check_accounts_status()), daemon=True).start(), 
               bg="#9C27B0", fg="white", width=12).pack(side=LEFT, padx=5)
        
        Button(account_btn_frame, text="➕ 导入Session", font=self.font_button, 
               command=self.import_session, 
               bg="#4CAF50", fg="white", width=12).pack(side=LEFT, padx=5)
        
        Button(account_btn_frame, text="✅ 全选", font=self.font_button, 
               command=self.select_all_accounts, 
               bg="#FF9800", fg="white", width=10).pack(side=LEFT, padx=5)
        
        Button(account_btn_frame, text="❌ 全不选", font=self.font_button, 
               command=self.deselect_all_accounts, 
               bg="#9E9E9E", fg="white", width=10).pack(side=LEFT, padx=5)
        
        Button(account_btn_frame, text="🗑️ 删除失效", font=self.font_button, 
               command=self.delete_invalid_accounts, 
               bg="#f44336", fg="white", width=10).pack(side=LEFT, padx=5)
        
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
        
        # 控制按钮
        control_frame = Frame(parent)
        control_frame.pack(fill=X, padx=10, pady=5)
        
        self.start_button = Button(control_frame, text="▶ 开始加群", 
                                   font=self.font_button, 
                                   command=self.start_join, 
                                   bg="#4CAF50", fg="white", width=15, height=2)
        self.start_button.pack(side=LEFT, padx=5)
        
        self.stop_button = Button(control_frame, text="⏸ 停止", 
                                  font=self.font_button, 
                                  command=self.stop_join, 
                                  bg="#f44336", fg="white", width=15, height=2, 
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
        
        # 间隔设置
        Label(config_frame, text="最小间隔(秒):", font=self.font_label).grid(row=0, column=0, sticky=W, pady=5)
        self.interval_min_var = IntVar(value=Config.INTERVAL_MIN)
        Entry(config_frame, textvariable=self.interval_min_var, font=self.font_label, width=10).grid(row=0, column=1, pady=5)
        
        Label(config_frame, text="最大间隔(秒):", font=self.font_label).grid(row=1, column=0, sticky=W, pady=5)
        self.interval_max_var = IntVar(value=Config.INTERVAL_MAX)
        Entry(config_frame, textvariable=self.interval_max_var, font=self.font_label, width=10).grid(row=1, column=1, pady=5)
        
        Label(config_frame, text="批次大小:", font=self.font_label).grid(row=2, column=0, sticky=W, pady=5)
        self.batch_size_var = IntVar(value=Config.BATCH_SIZE)
        Entry(config_frame, textvariable=self.batch_size_var, font=self.font_label, width=10).grid(row=2, column=1, pady=5)
        
        Label(config_frame, text="批次休息最小(秒):", font=self.font_label).grid(row=3, column=0, sticky=W, pady=5)
        self.batch_rest_min_var = IntVar(value=Config.BATCH_REST_MIN)
        Entry(config_frame, textvariable=self.batch_rest_min_var, font=self.font_label, width=10).grid(row=3, column=1, pady=5)
        
        Label(config_frame, text="批次休息最大(秒):", font=self.font_label).grid(row=4, column=0, sticky=W, pady=5)
        self.batch_rest_max_var = IntVar(value=Config.BATCH_REST_MAX)
        Entry(config_frame, textvariable=self.batch_rest_max_var, font=self.font_label, width=10).grid(row=4, column=1, pady=5)
        
        Label(config_frame, text="每日限额:", font=self.font_label).grid(row=5, column=0, sticky=W, pady=5)
        self.daily_limit_var = IntVar(value=Config.DAILY_LIMIT)
        Entry(config_frame, textvariable=self.daily_limit_var, font=self.font_label, width=10).grid(row=5, column=1, pady=5)
        
        # 保存按钮
        Button(config_frame, text="💾 保存配置", font=self.font_button,
               command=self.save_config, bg="#4CAF50", fg="white", width=15).grid(row=6, column=0, columnspan=2, pady=20)
    
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
        Config.BATCH_SIZE = self.batch_size_var.get()
        Config.BATCH_REST_MIN = self.batch_rest_min_var.get()
        Config.BATCH_REST_MAX = self.batch_rest_max_var.get()
        Config.DAILY_LIMIT = self.daily_limit_var.get()
        
        self.log("✅ 配置已保存", "SUCCESS")
        messagebox.showinfo("成功", "配置已保存！")
    
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
                f"{account.joined_count}/{account.daily_limit}"
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
                f"{account.joined_count}/{account.daily_limit}"
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
        self.log("=" * 60, "INFO")
        self.log(f"🚀 开始加群！使用 {len(self.selected_accounts)} 个账号（并发）", "INFO")
        self.log(f"🔍 调试: selected_accounts = {self.selected_accounts}", "INFO")
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
        
        # 为每个账号创建任务
        tasks = []
        for account_idx, session_name in enumerate(self.selected_accounts):
            task = self.account_worker(session_name, groups, account_idx)
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
        # 错开启动时间（避免所有账号同时请求）
        initial_delay = random.randint(Config.ACCOUNT_INTERVAL_MIN, Config.ACCOUNT_INTERVAL_MAX) * account_idx
        if initial_delay > 0:
            self.log(f"⏳ [{session_name}] 等待 {initial_delay} 秒后开始...", "INFO")
            await asyncio.sleep(initial_delay)
        
        self.log(f"🚀 [{session_name}] 开始加群！", "INFO")
        
        success = 0
        failed = 0
        
        for idx, link in enumerate(groups):
            if not self.is_running:
                self.log(f"⏸️  [{session_name}] 已停止", "WARNING")
                break
            
            # 加入群
            result = await self.join_group(session_name, link)
            if result:
                success += 1
            else:
                failed += 1
            
            # 智能间隔（避免被限流）
            if idx < len(groups) - 1:  # 不是最后一个群
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
                self.log(f"❌ [{session_name}] 未授权", "ERROR")
                return False
            
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
            return True
        
        except errors.UserAlreadyParticipantError:
            DataManager.mark_joined(session_name, link)
            self.log(f"ℹ️  [{session_name}] 已在群里: {link}", "INFO")
            self.remove_group_link(link)  # 删除已加入的群链接
            return True
        
        except Exception as e:
            error_msg = str(e)
            if 'successfully requested to join' in error_msg.lower():
                DataManager.mark_joined(session_name, link)
                self.log(f"✅ [{session_name}] 已申请入群，待审核: {link} ⏳", "SUCCESS")
                self.remove_group_link(link)  # 删除已申请的群链接
                return True
            
            # 判断是否是永久失败（删除链接）
            if any(keyword in error_msg.lower() for keyword in ['not found', 'invalid', 'private', 'banned']):
                self.log(f"❌ [{session_name}] 失败（永久）: {link} - {e}", "ERROR")
                self.remove_group_link(link)  # 删除失效链接
            else:
                self.log(f"❌ [{session_name}] 失败（临时）: {link} - {e}", "ERROR")
            
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
