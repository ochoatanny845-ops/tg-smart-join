#!/usr/bin/env python3
"""
Telegram 智能加群工具 - GUI版本
- Tkinter图形界面
- 实时日志显示
- 进度条展示
- 账号管理
- 群链接管理
"""

import asyncio
import random
import re
import json
import os
import logging
import threading
from datetime import datetime
from typing import List, Dict, Optional
from tkinter import *
from tkinter import ttk, scrolledtext, filedialog, messagebox
from telethon import TelegramClient, errors
from telethon.tl.types import Channel, Chat
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

# ===== 配置 =====
class Config:
    # API配置（默认配置）
    API_ID = 2040
    API_HASH = 'b18441a1ff607e10a989891a5462e627'
    
    # 文件路径
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    SESSIONS_DIR = os.path.join(BASE_DIR, 'sessions')
    GROUPS_FILE = os.path.join(BASE_DIR, 'groups.txt')
    JOINED_FILE = os.path.join(BASE_DIR, 'joined.json')
    LOG_FILE = os.path.join(BASE_DIR, 'smart_join.log')
    CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
    
    # 智能间隔配置（秒）
    INTERVAL_MIN = 30
    INTERVAL_MAX = 120
    BATCH_SIZE = 5
    BATCH_REST_MIN = 300
    BATCH_REST_MAX = 600
    DAILY_LIMIT = 30
    
    # 创建必要目录
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    
    @classmethod
    def load_config(cls):
        """加载保存的配置"""
        if os.path.exists(cls.CONFIG_FILE):
            try:
                with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    cls.INTERVAL_MIN = data.get('interval_min', 30)
                    cls.INTERVAL_MAX = data.get('interval_max', 120)
                    cls.BATCH_SIZE = data.get('batch_size', 5)
                    cls.BATCH_REST_MIN = data.get('batch_rest_min', 300)
                    cls.BATCH_REST_MAX = data.get('batch_rest_max', 600)
                    cls.DAILY_LIMIT = data.get('daily_limit', 30)
            except:
                pass
    
    @classmethod
    def save_config(cls):
        """保存配置"""
        data = {
            'interval_min': cls.INTERVAL_MIN,
            'interval_max': cls.INTERVAL_MAX,
            'batch_size': cls.BATCH_SIZE,
            'batch_rest_min': cls.BATCH_REST_MIN,
            'batch_rest_max': cls.BATCH_REST_MAX,
            'daily_limit': cls.DAILY_LIMIT
        }
        with open(cls.CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

# ===== 加群管理器 =====
class SmartJoinManager:
    def __init__(self):
        self.joined_data = self.load_joined_data()
        
    def load_joined_data(self) -> Dict:
        if os.path.exists(Config.JOINED_FILE):
            try:
                with open(Config.JOINED_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {'groups': {}, 'daily_count': 0, 'last_date': ''}
        return {'groups': {}, 'daily_count': 0, 'last_date': ''}
    
    def save_joined_data(self):
        with open(Config.JOINED_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.joined_data, f, ensure_ascii=False, indent=2)
    
    def is_joined(self, link: str) -> bool:
        return link in self.joined_data['groups']
    
    def mark_joined(self, link: str, group_title: str = ''):
        self.joined_data['groups'][link] = {
            'title': group_title,
            'joined_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.save_joined_data()
    
    def check_daily_limit(self) -> bool:
        today = datetime.now().strftime('%Y-%m-%d')
        if self.joined_data['last_date'] != today:
            self.joined_data['daily_count'] = 0
            self.joined_data['last_date'] = today
            self.save_joined_data()
            return True
        return self.joined_data['daily_count'] < Config.DAILY_LIMIT
    
    def increment_daily_count(self):
        self.joined_data['daily_count'] += 1
        self.save_joined_data()

# ===== 群链接解析器 =====
class GroupLinkParser:
    @staticmethod
    def parse_link(link: str) -> Optional[Dict]:
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
        
        return None

# ===== GUI应用 =====
class SmartJoinGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Telegram 智能加群工具 v1.0 GUI")
        self.root.geometry("900x700")
        self.root.resizable(True, True)
        
        # 加载配置
        Config.load_config()
        
        # 状态变量
        self.is_running = False
        self.stop_requested = False
        self.client = None
        self.manager = SmartJoinManager()
        
        # 创建UI
        self.setup_ui()
        
        # 加载数据
        self.load_sessions()
        self.load_groups()
        self.update_stats()
    
    def setup_ui(self):
        """创建UI界面"""
        
        # 创建Notebook（标签页）
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        # 标签页1: 主界面
        main_frame = Frame(notebook)
        notebook.add(main_frame, text="加群操作")
        self.setup_main_tab(main_frame)
        
        # 标签页2: 群链接管理
        groups_frame = Frame(notebook)
        notebook.add(groups_frame, text="群链接管理")
        self.setup_groups_tab(groups_frame)
        
        # 标签页3: 配置
        config_frame = Frame(notebook)
        notebook.add(config_frame, text="配置")
        self.setup_config_tab(config_frame)
        
        # 标签页4: 统计
        stats_frame = Frame(notebook)
        notebook.add(stats_frame, text="统计")
        self.setup_stats_tab(stats_frame)
    
    def setup_main_tab(self, parent):
        """主界面标签页"""
        
        # 账号选择区域
        account_frame = LabelFrame(parent, text="账号选择", padx=10, pady=10)
        account_frame.pack(fill=X, padx=10, pady=5)
        
        Label(account_frame, text="Session账号:").grid(row=0, column=0, sticky=W)
        self.session_var = StringVar()
        self.session_combo = ttk.Combobox(account_frame, textvariable=self.session_var, state='readonly', width=40)
        self.session_combo.grid(row=0, column=1, padx=5)
        
        Button(account_frame, text="刷新", command=self.load_sessions).grid(row=0, column=2, padx=5)
        Button(account_frame, text="导入Session", command=self.import_session).grid(row=0, column=3, padx=5)
        
        # 统计信息
        stats_frame = LabelFrame(parent, text="统计信息", padx=10, pady=10)
        stats_frame.pack(fill=X, padx=10, pady=5)
        
        self.total_groups_label = Label(stats_frame, text="总群数: 0", font=("Arial", 10))
        self.total_groups_label.grid(row=0, column=0, padx=10)
        
        self.joined_groups_label = Label(stats_frame, text="已加入: 0", font=("Arial", 10), fg="green")
        self.joined_groups_label.grid(row=0, column=1, padx=10)
        
        self.pending_groups_label = Label(stats_frame, text="待加入: 0", font=("Arial", 10), fg="orange")
        self.pending_groups_label.grid(row=0, column=2, padx=10)
        
        self.daily_count_label = Label(stats_frame, text="今日已加: 0/30", font=("Arial", 10), fg="blue")
        self.daily_count_label.grid(row=0, column=3, padx=10)
        
        # 进度条
        progress_frame = Frame(parent)
        progress_frame.pack(fill=X, padx=10, pady=5)
        
        self.progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress.pack(fill=X, pady=5)
        
        self.progress_label = Label(progress_frame, text="就绪", font=("Arial", 9))
        self.progress_label.pack()
        
        # 控制按钮
        button_frame = Frame(parent)
        button_frame.pack(fill=X, padx=10, pady=5)
        
        self.start_button = Button(button_frame, text="▶ 开始加群", command=self.start_join, 
                                   bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), width=15)
        self.start_button.pack(side=LEFT, padx=5)
        
        self.stop_button = Button(button_frame, text="⏸ 停止", command=self.stop_join, 
                                 bg="#f44336", fg="white", font=("Arial", 12, "bold"), width=15, state=DISABLED)
        self.stop_button.pack(side=LEFT, padx=5)
        
        Button(button_frame, text="清空日志", command=self.clear_log).pack(side=RIGHT, padx=5)
        
        # 日志区域
        log_frame = LabelFrame(parent, text="运行日志", padx=5, pady=5)
        log_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, wrap=WORD, 
                                                  font=("Consolas", 9))
        self.log_text.pack(fill=BOTH, expand=True)
        
        # 配置颜色标签
        self.log_text.tag_config("INFO", foreground="black")
        self.log_text.tag_config("SUCCESS", foreground="green")
        self.log_text.tag_config("WARNING", foreground="orange")
        self.log_text.tag_config("ERROR", foreground="red")
    
    def setup_groups_tab(self, parent):
        """群链接管理标签页"""
        
        # 工具栏
        toolbar = Frame(parent)
        toolbar.pack(fill=X, padx=10, pady=5)
        
        Button(toolbar, text="导入群链接", command=self.import_groups).pack(side=LEFT, padx=5)
        Button(toolbar, text="导出群链接", command=self.export_groups).pack(side=LEFT, padx=5)
        Button(toolbar, text="清空列表", command=self.clear_groups).pack(side=LEFT, padx=5)
        Button(toolbar, text="获取邀请链接", command=self.show_invite_link_help, 
               bg="#FF9800", fg="white").pack(side=LEFT, padx=5)
        Button(toolbar, text="刷新统计", command=self.update_stats).pack(side=RIGHT, padx=5)
        
        # 提示框
        tip_frame = Frame(parent, bg="#FFF3E0", relief=RIDGE, bd=2)
        tip_frame.pack(fill=X, padx=10, pady=5)
        
        tip_text = """💡 重要提示：建议使用邀请链接格式！
        
✅ 推荐格式：https://t.me/+XXXXX 或 https://t.me/joinchat/XXXXX
❌ 避免使用：@username 或 https://t.me/username （可能被风控，搜索不到）

获取邀请链接方法：
1. 在Telegram中打开群组
2. 点击群名 → 点击"添加成员" → 点击"邀请链接"
3. 复制链接（格式：https://t.me/+XXXXX）
"""
        
        Label(tip_frame, text=tip_text, bg="#FFF3E0", fg="#E65100", 
              justify=LEFT, font=("Arial", 9), padx=10, pady=5).pack()
        
        # 群链接列表
        list_frame = LabelFrame(parent, text="群链接列表 (每行一个)", padx=5, pady=5)
        list_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        self.groups_text = scrolledtext.ScrolledText(list_frame, height=15, wrap=WORD, 
                                                     font=("Consolas", 10))
        self.groups_text.pack(fill=BOTH, expand=True)
        
        # 保存按钮
        Button(parent, text="💾 保存群链接", command=self.save_groups, 
               bg="#2196F3", fg="white", font=("Arial", 11, "bold")).pack(pady=10)
    
    def setup_config_tab(self, parent):
        """配置标签页"""
        
        config_frame = LabelFrame(parent, text="智能间隔配置", padx=20, pady=20)
        config_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        # 普通间隔
        Label(config_frame, text="普通间隔 (秒):", font=("Arial", 10)).grid(row=0, column=0, sticky=W, pady=5)
        
        interval_frame = Frame(config_frame)
        interval_frame.grid(row=0, column=1, sticky=W, pady=5)
        
        Label(interval_frame, text="最小:").pack(side=LEFT)
        self.interval_min_var = IntVar(value=Config.INTERVAL_MIN)
        Spinbox(interval_frame, from_=10, to=300, textvariable=self.interval_min_var, width=10).pack(side=LEFT, padx=5)
        
        Label(interval_frame, text="最大:").pack(side=LEFT, padx=(20, 0))
        self.interval_max_var = IntVar(value=Config.INTERVAL_MAX)
        Spinbox(interval_frame, from_=30, to=600, textvariable=self.interval_max_var, width=10).pack(side=LEFT, padx=5)
        
        # 批次设置
        Label(config_frame, text="批次大小:", font=("Arial", 10)).grid(row=1, column=0, sticky=W, pady=5)
        self.batch_size_var = IntVar(value=Config.BATCH_SIZE)
        Spinbox(config_frame, from_=1, to=20, textvariable=self.batch_size_var, width=10).grid(row=1, column=1, sticky=W, pady=5)
        
        # 批次休息
        Label(config_frame, text="批次休息 (秒):", font=("Arial", 10)).grid(row=2, column=0, sticky=W, pady=5)
        
        batch_rest_frame = Frame(config_frame)
        batch_rest_frame.grid(row=2, column=1, sticky=W, pady=5)
        
        Label(batch_rest_frame, text="最小:").pack(side=LEFT)
        self.batch_rest_min_var = IntVar(value=Config.BATCH_REST_MIN)
        Spinbox(batch_rest_frame, from_=60, to=1800, textvariable=self.batch_rest_min_var, width=10).pack(side=LEFT, padx=5)
        
        Label(batch_rest_frame, text="最大:").pack(side=LEFT, padx=(20, 0))
        self.batch_rest_max_var = IntVar(value=Config.BATCH_REST_MAX)
        Spinbox(batch_rest_frame, from_=120, to=3600, textvariable=self.batch_rest_max_var, width=10).pack(side=LEFT, padx=5)
        
        # 每日限额
        Label(config_frame, text="每日限额:", font=("Arial", 10)).grid(row=3, column=0, sticky=W, pady=5)
        self.daily_limit_var = IntVar(value=Config.DAILY_LIMIT)
        Spinbox(config_frame, from_=1, to=100, textvariable=self.daily_limit_var, width=10).grid(row=3, column=1, sticky=W, pady=5)
        
        # 保存按钮
        Button(config_frame, text="💾 保存配置", command=self.save_config, 
               bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), width=20).grid(row=4, column=0, columnspan=2, pady=20)
        
        # 说明文字
        info_text = """
        配置说明：
        • 普通间隔：每次加群之间的等待时间（随机）
        • 批次大小：连续加几个群后休息
        • 批次休息：每批次之间的休息时间（随机）
        • 每日限额：每天最多加多少个群（避免被封）
        
        建议：
        - 新账号：减小批次大小，增大间隔
        - 老账号：可以适当增加限额
        - 谨慎操作：宁可慢一点，也不要触发限流
        """
        
        info_frame = LabelFrame(parent, text="说明", padx=10, pady=10)
        info_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        info_label = Label(info_frame, text=info_text, justify=LEFT, font=("Arial", 9))
        info_label.pack()
    
    def setup_stats_tab(self, parent):
        """统计标签页"""
        
        stats_frame = LabelFrame(parent, text="已加入群组列表", padx=10, pady=10)
        stats_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        # 创建Treeview
        columns = ("群名", "加入时间", "链接")
        self.stats_tree = ttk.Treeview(stats_frame, columns=columns, show='headings', height=20)
        
        self.stats_tree.heading("群名", text="群名")
        self.stats_tree.heading("加入时间", text="加入时间")
        self.stats_tree.heading("链接", text="链接")
        
        self.stats_tree.column("群名", width=200)
        self.stats_tree.column("加入时间", width=150)
        self.stats_tree.column("链接", width=300)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(stats_frame, orient=VERTICAL, command=self.stats_tree.yview)
        self.stats_tree.configure(yscrollcommand=scrollbar.set)
        
        self.stats_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        # 按钮
        button_frame = Frame(parent)
        button_frame.pack(fill=X, padx=10, pady=5)
        
        Button(button_frame, text="刷新列表", command=self.update_stats_tree).pack(side=LEFT, padx=5)
        Button(button_frame, text="导出CSV", command=self.export_stats).pack(side=LEFT, padx=5)
        Button(button_frame, text="清空记录", command=self.clear_stats).pack(side=LEFT, padx=5)
        
        # 加载数据
        self.update_stats_tree()
    
    # ===== 数据加载 =====
    
    def load_sessions(self):
        """加载Session列表"""
        sessions = [f.replace('.session', '') for f in os.listdir(Config.SESSIONS_DIR) 
                   if f.endswith('.session')]
        self.session_combo['values'] = sessions
        if sessions:
            self.session_combo.current(0)
    
    def load_groups(self):
        """加载群链接"""
        if os.path.exists(Config.GROUPS_FILE):
            with open(Config.GROUPS_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
                self.groups_text.delete('1.0', END)
                self.groups_text.insert('1.0', content)
    
    def save_groups(self):
        """保存群链接"""
        content = self.groups_text.get('1.0', END).strip()
        with open(Config.GROUPS_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
        self.log("✅ 群链接已保存", "SUCCESS")
        self.update_stats()
    
    def import_groups(self):
        """导入群链接文件"""
        filepath = filedialog.askopenfilename(
            title="选择群链接文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if filepath:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                self.groups_text.insert(END, "\n" + content)
            self.log(f"✅ 已导入: {filepath}", "SUCCESS")
    
    def export_groups(self):
        """导出群链接"""
        filepath = filedialog.asksaveasfilename(
            title="保存群链接",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt")]
        )
        if filepath:
            content = self.groups_text.get('1.0', END)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            self.log(f"✅ 已导出: {filepath}", "SUCCESS")
    
    def clear_groups(self):
        """清空群链接"""
        if messagebox.askyesno("确认", "确定要清空所有群链接吗？"):
            self.groups_text.delete('1.0', END)
            self.log("⚠️ 群链接列表已清空", "WARNING")
    
    def import_session(self):
        """导入Session文件"""
        filepath = filedialog.askopenfilename(
            title="选择Session文件",
            filetypes=[("Session文件", "*.session"), ("所有文件", "*.*")]
        )
        if filepath:
            import shutil
            filename = os.path.basename(filepath)
            dest = os.path.join(Config.SESSIONS_DIR, filename)
            shutil.copy2(filepath, dest)
            self.log(f"✅ 已导入Session: {filename}", "SUCCESS")
            self.load_sessions()
    
    def save_config(self):
        """保存配置"""
        Config.INTERVAL_MIN = self.interval_min_var.get()
        Config.INTERVAL_MAX = self.interval_max_var.get()
        Config.BATCH_SIZE = self.batch_size_var.get()
        Config.BATCH_REST_MIN = self.batch_rest_min_var.get()
        Config.BATCH_REST_MAX = self.batch_rest_max_var.get()
        Config.DAILY_LIMIT = self.daily_limit_var.get()
        Config.save_config()
        self.log("✅ 配置已保存", "SUCCESS")
        messagebox.showinfo("成功", "配置已保存！")
    
    def update_stats(self):
        """更新统计信息"""
        # 读取群链接
        content = self.groups_text.get('1.0', END).strip()
        links = [line.strip() for line in content.split('\n') 
                if line.strip() and not line.startswith('#')]
        
        total = len(links)
        joined = sum(1 for link in links if self.manager.is_joined(link))
        pending = total - joined
        daily = self.manager.joined_data.get('daily_count', 0)
        
        self.total_groups_label.config(text=f"总群数: {total}")
        self.joined_groups_label.config(text=f"已加入: {joined}")
        self.pending_groups_label.config(text=f"待加入: {pending}")
        self.daily_count_label.config(text=f"今日已加: {daily}/{Config.DAILY_LIMIT}")
    
    def update_stats_tree(self):
        """更新统计列表"""
        # 清空现有数据
        for item in self.stats_tree.get_children():
            self.stats_tree.delete(item)
        
        # 加载已加入群组
        for link, info in self.manager.joined_data.get('groups', {}).items():
            self.stats_tree.insert('', END, values=(
                info.get('title', '未知'),
                info.get('joined_at', ''),
                link
            ))
    
    def export_stats(self):
        """导出统计数据"""
        filepath = filedialog.asksaveasfilename(
            title="保存统计数据",
            defaultextension=".csv",
            filetypes=[("CSV文件", "*.csv")]
        )
        if filepath:
            import csv
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['群名', '加入时间', '链接'])
                for link, info in self.manager.joined_data.get('groups', {}).items():
                    writer.writerow([info.get('title', ''), info.get('joined_at', ''), link])
            self.log(f"✅ 已导出: {filepath}", "SUCCESS")
    
    def clear_stats(self):
        """清空统计记录"""
        if messagebox.askyesno("确认", "确定要清空所有加群记录吗？\n这将重置今日计数和已加入群组列表！"):
            self.manager.joined_data = {'groups': {}, 'daily_count': 0, 'last_date': ''}
            self.manager.save_joined_data()
            self.update_stats()
            self.update_stats_tree()
            self.log("⚠️ 统计记录已清空", "WARNING")
    
    def show_invite_link_help(self):
        """显示邀请链接获取帮助"""
        help_text = """如何获取群组邀请链接：

1. 在Telegram中打开目标群组

2. 点击群名称（顶部）

3. 点击"添加成员"按钮

4. 点击"邀请链接"

5. 复制链接（格式：https://t.me/+XXXXX）

6. 粘贴到"群链接列表"中

---

为什么要用邀请链接而不是@username？

• @username 可能被风控，搜索不到
• 邀请链接直接加入，成功率更高
• 避免触发Telegram的反spam检测

---

支持的链接格式：
✅ https://t.me/+XXXXX （推荐）
✅ https://t.me/joinchat/XXXXX
✅ https://t.me/username （可能失败）
✅ @username （可能失败）
"""
        messagebox.showinfo("获取邀请链接帮助", help_text)
    
    # ===== 日志 =====
    
    def log(self, message, level="INFO"):
        """输出日志"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_message = f"[{timestamp}] {message}\n"
        
        self.log_text.insert(END, log_message, level)
        self.log_text.see(END)
        self.root.update()
    
    def clear_log(self):
        """清空日志"""
        self.log_text.delete('1.0', END)
    
    # ===== 加群逻辑 =====
    
    def start_join(self):
        """开始加群"""
        if not self.session_var.get():
            messagebox.showerror("错误", "请先选择Session账号！")
            return
        
        # 检查群链接
        content = self.groups_text.get('1.0', END).strip()
        if not content:
            messagebox.showerror("错误", "请先添加群链接！")
            return
        
        self.is_running = True
        self.stop_requested = False
        self.start_button.config(state=DISABLED)
        self.stop_button.config(state=NORMAL)
        
        # 在新线程中运行
        thread = threading.Thread(target=self.run_join_task, daemon=True)
        thread.start()
    
    def stop_join(self):
        """停止加群"""
        self.stop_requested = True
        self.log("⏸️ 正在停止...", "WARNING")
    
    def run_join_task(self):
        """运行加群任务（在新线程中）"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.join_groups_async())
        loop.close()
    
    async def join_groups_async(self):
        """异步加群"""
        try:
            # 启动客户端
            session_path = os.path.join(Config.SESSIONS_DIR, self.session_var.get())
            self.log(f"📱 正在连接Telegram...", "INFO")
            self.client = TelegramClient(session_path, Config.API_ID, Config.API_HASH)
            
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                self.log("❌ Session未授权！", "ERROR")
                messagebox.showerror("错误", "Session未授权，请重新登录或更换Session文件！")
                return
            
            # 获取账号信息（添加异常处理）
            try:
                me = await self.client.get_me()
                phone = me.phone if me.phone else "未知"
                username = me.username if me.username else "无"
                self.log(f"✅ 登录成功: {me.first_name} (@{username}) +{phone}", "SUCCESS")
            except Exception as e:
                self.log(f"⚠️ 无法获取账号信息: {e}", "WARNING")
                self.log(f"⚠️ 继续尝试加群...", "WARNING")
            
            # 读取群链接
            content = self.groups_text.get('1.0', END).strip()
            links = [line.strip() for line in content.split('\n') 
                    if line.strip() and not line.startswith('#')]
            
            # 过滤已加入的群
            pending_links = [link for link in links if not self.manager.is_joined(link)]
            
            total = len(pending_links)
            if total == 0:
                self.log("ℹ️ 所有群都已加入！", "INFO")
                messagebox.showinfo("提示", "所有群都已加入！")
                return
            
            self.log(f"📋 待加入 {total} 个群", "INFO")
            
            success_count = 0
            
            for idx, link in enumerate(pending_links, 1):
                if self.stop_requested:
                    self.log("⏸️ 已停止", "WARNING")
                    break
                
                # 更新进度
                progress = int(idx * 100 / total)
                self.progress['value'] = progress
                self.progress_label.config(text=f"进度: {idx}/{total} ({progress}%)")
                
                # 检查每日限额
                if not self.manager.check_daily_limit():
                    self.log(f"⚠️ 已达到每日限额 ({Config.DAILY_LIMIT}个)", "WARNING")
                    break
                
                # 加群
                success = await self.join_group(link)
                if success:
                    success_count += 1
                
                # 智能间隔
                if idx < total and not self.stop_requested:
                    if idx % Config.BATCH_SIZE == 0:
                        # 批次休息
                        rest_time = random.randint(Config.BATCH_REST_MIN, Config.BATCH_REST_MAX)
                        self.log(f"⏸️ 完成一批次，休息 {rest_time} 秒...", "INFO")
                        for i in range(rest_time):
                            if self.stop_requested:
                                break
                            self.progress_label.config(text=f"休息中... {rest_time-i} 秒")
                            await asyncio.sleep(1)
                    else:
                        # 普通间隔
                        interval = random.randint(Config.INTERVAL_MIN, Config.INTERVAL_MAX)
                        self.log(f"⏸️ 等待 {interval} 秒...", "INFO")
                        for i in range(interval):
                            if self.stop_requested:
                                break
                            self.progress_label.config(text=f"等待中... {interval-i} 秒")
                            await asyncio.sleep(1)
                
                # 更新统计
                self.update_stats()
            
            # 完成
            self.log(f"\n{'='*60}", "INFO")
            self.log(f"🎉 加群完成！", "SUCCESS")
            self.log(f"✅ 成功: {success_count} 个", "SUCCESS")
            self.log(f"📊 今日已加: {self.manager.joined_data['daily_count']}/{Config.DAILY_LIMIT}", "INFO")
            
            messagebox.showinfo("完成", f"加群完成！\n成功: {success_count} 个")
            
        except Exception as e:
            self.log(f"❌ 错误: {e}", "ERROR")
            messagebox.showerror("错误", str(e))
        
        finally:
            if self.client:
                await self.client.disconnect()
            
            self.is_running = False
            self.start_button.config(state=NORMAL)
            self.stop_button.config(state=DISABLED)
            self.progress['value'] = 0
            self.progress_label.config(text="就绪")
    
    async def join_group(self, link: str) -> bool:
        """加入单个群"""
        parsed = GroupLinkParser.parse_link(link)
        if not parsed:
            self.log(f"⚠️ 无法解析: {link}", "WARNING")
            return False
        
        try:
            group_title = ''
            
            if parsed['type'] == 'invite':
                result = await self.client(ImportChatInviteRequest(parsed['hash']))
                if hasattr(result, 'chats') and result.chats:
                    group_title = result.chats[0].title
                self.log(f"✅ 成功加入私有群: {group_title}", "SUCCESS")
                
            elif parsed['type'] == 'username':
                # 使用ResolveUsernameRequest替代get_entity，避免搜索问题
                from telethon.tl.functions.contacts import ResolveUsernameRequest
                
                try:
                    # 直接解析用户名为实体
                    result = await self.client(ResolveUsernameRequest(parsed['username']))
                    
                    if result.chats:
                        chat = result.chats[0]
                        # 加入频道/群组
                        await self.client(JoinChannelRequest(chat))
                        group_title = getattr(chat, 'title', parsed['username'])
                        self.log(f"✅ 成功加入公开群: {group_title} (@{parsed['username']})", "SUCCESS")
                    else:
                        self.log(f"⚠️ 未找到群组: @{parsed['username']}", "WARNING")
                        return False
                        
                except errors.UsernameNotOccupiedError:
                    self.log(f"❌ 用户名不存在: @{parsed['username']}", "ERROR")
                    self.log(f"💡 建议使用邀请链接格式: https://t.me/+XXXXX", "WARNING")
                    return False
                except errors.UsernameInvalidError:
                    self.log(f"❌ 用户名格式无效: @{parsed['username']}", "ERROR")
                    return False
            
            self.manager.mark_joined(link, group_title)
            self.manager.increment_daily_count()
            return True
            
        except errors.FloodWaitError as e:
            self.log(f"❌ 触发限流，需等待 {e.seconds} 秒", "ERROR")
            await asyncio.sleep(e.seconds)
            return False
            
        except errors.InviteHashExpiredError:
            self.log(f"❌ 邀请链接已过期: {link}", "ERROR")
            return False
            
        except errors.InviteHashInvalidError:
            self.log(f"❌ 邀请链接无效: {link}", "ERROR")
            return False
            
        except errors.UserAlreadyParticipantError:
            self.log(f"ℹ️ 已经在群里了: {link}", "INFO")
            self.manager.mark_joined(link)
            return False
            
        except errors.ChannelPrivateError:
            self.log(f"❌ 群组已私有或被封禁: {link}", "ERROR")
            return False
            
        except Exception as e:
            self.log(f"❌ 加入失败: {link} - {e}", "ERROR")
            return False

# ===== 主程序 =====
def main():
    root = Tk()
    app = SmartJoinGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()
