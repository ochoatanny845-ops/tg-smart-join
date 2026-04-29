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
    
    INTERVAL_MIN = 30
    INTERVAL_MAX = 120
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
        self.session_name = session_name
        self.phone = ''
        self.name = ''
        self.status = '未知'
        self.joined_count = 0
        self.daily_limit = Config.DAILY_LIMIT
        self.is_authorized = False
    
    async def load_info(self):
        """加载账号信息"""
        session_path = os.path.join(Config.SESSIONS_DIR, self.session_name)
        client = TelegramClient(session_path, Config.API_ID, Config.API_HASH)
        
        try:
            await client.connect()
            
            if await client.is_user_authorized():
                me = await client.get_me()
                self.phone = f'+{me.phone}' if me.phone else '未知'
                self.name = me.first_name or '未知'
                self.status = '✅ 正常'
                self.is_authorized = True
            else:
                self.status = '❌ 未授权'
                self.is_authorized = False
            
            # 加载已加入群数
            self.joined_count = DataManager.get_joined_count(self.session_name)
            
        except Exception as e:
            self.status = f'❌ 错误: {e}'
            self.is_authorized = False
        
        finally:
            await client.disconnect()

# ===== 改进版GUI =====
class SmartJoinGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Telegram 智能加群工具 v2.0 - 改进版")
        self.root.geometry("1000x700")
        
        # 放大字体
        self.font_label = ("Arial", 11)
        self.font_button = ("Arial", 14, "bold")
        self.font_menu = ("Arial", 12)
        self.font_log = ("Consolas", 10)
        
        # 数据
        self.accounts = []  # AccountInfo列表
        self.selected_accounts = []  # 选中的账号
        self.is_running = False
        
        # 创建UI
        self.setup_ui()
        
        # 加载账号
        asyncio.run(self.load_accounts())
    
    def setup_ui(self):
        """创建UI"""
        
        # 顶部：账号列表
        account_frame = LabelFrame(self.root, text="📱 账号列表", 
                                   font=self.font_menu, padx=10, pady=10)
        account_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # 账号表格
        columns = ('选择', '手机号', '名字', '状态', '已加群数', 'Session文件')
        self.account_tree = ttk.Treeview(account_frame, columns=columns, 
                                        show='headings', height=8)
        
        # 列宽
        self.account_tree.column('选择', width=50, anchor=CENTER)
        self.account_tree.column('手机号', width=120, anchor=CENTER)
        self.account_tree.column('名字', width=100, anchor=CENTER)
        self.account_tree.column('状态', width=100, anchor=CENTER)
        self.account_tree.column('已加群数', width=100, anchor=CENTER)
        self.account_tree.column('Session文件', width=200, anchor=W)
        
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
        account_btn_frame = Frame(self.root)
        account_btn_frame.pack(fill=X, padx=10, pady=5)
        
        Button(account_btn_frame, text="🔄 刷新列表", font=self.font_button, 
               command=lambda: asyncio.run(self.load_accounts()), 
               bg="#2196F3", fg="white", width=12).pack(side=LEFT, padx=5)
        
        Button(account_btn_frame, text="➕ 导入Session", font=self.font_button, 
               command=self.import_session, 
               bg="#4CAF50", fg="white", width=12).pack(side=LEFT, padx=5)
        
        Button(account_btn_frame, text="✅ 全选", font=self.font_button, 
               command=self.select_all_accounts, 
               bg="#FF9800", fg="white", width=10).pack(side=LEFT, padx=5)
        
        Button(account_btn_frame, text="❌ 全不选", font=self.font_button, 
               command=self.deselect_all_accounts, 
               bg="#9E9E9E", fg="white", width=10).pack(side=LEFT, padx=5)
        
        # 统计信息
        stats_frame = LabelFrame(self.root, text="📊 统计信息", 
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
        control_frame = Frame(self.root)
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
        self.progress = ttk.Progressbar(self.root, mode='determinate')
        self.progress.pack(fill=X, padx=10, pady=5)
        
        self.progress_label = Label(self.root, text="就绪", font=self.font_label)
        self.progress_label.pack()
        
        # 日志
        log_frame = LabelFrame(self.root, text="📜 运行日志", 
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
    
    async def load_accounts(self):
        """加载所有账号信息"""
        self.log("🔍 扫描Session文件...", "INFO")
        
        # 清空表格
        for item in self.account_tree.get_children():
            self.account_tree.delete(item)
        
        self.accounts = []
        
        # 扫描sessions目录
        if not os.path.exists(Config.SESSIONS_DIR):
            os.makedirs(Config.SESSIONS_DIR)
            self.log("⚠️  sessions目录为空，请导入Session文件！", "WARNING")
            return
        
        session_files = [f.replace('.session', '') 
                        for f in os.listdir(Config.SESSIONS_DIR) 
                        if f.endswith('.session')]
        
        if not session_files:
            self.log("⚠️  未找到Session文件！", "WARNING")
            return
        
        self.log(f"📂 发现 {len(session_files)} 个Session文件", "INFO")
        
        # 加载每个账号信息
        for session_name in session_files:
            account = AccountInfo(session_name)
            await account.load_info()
            self.accounts.append(account)
            
            # 添加到表格
            values = (
                '☐',  # 未选中
                account.phone,
                account.name,
                account.status,
                f"{account.joined_count}/{account.daily_limit}",
                session_name
            )
            self.account_tree.insert('', END, values=values, tags=(session_name,))
            
            self.log(f"✅ {account.phone} ({account.name}) - {account.status}", 
                    "SUCCESS" if account.is_authorized else "WARNING")
        
        # 更新统计
        self.update_stats()
        self.log(f"✅ 加载完成！共 {len(self.accounts)} 个账号", "SUCCESS")
    
    def toggle_account_selection(self, event):
        """切换账号选择状态"""
        item = self.account_tree.selection()[0]
        session_name = self.account_tree.item(item)['tags'][0]
        
        # 切换选中状态
        current_values = list(self.account_tree.item(item)['values'])
        if current_values[0] == '☐':
            current_values[0] = '☑'
            if session_name not in self.selected_accounts:
                self.selected_accounts.append(session_name)
        else:
            current_values[0] = '☐'
            if session_name in self.selected_accounts:
                self.selected_accounts.remove(session_name)
        
        self.account_tree.item(item, values=current_values)
        self.update_stats()
    
    def select_all_accounts(self):
        """全选"""
        self.selected_accounts = []
        for item in self.account_tree.get_children():
            values = list(self.account_tree.item(item)['values'])
            values[0] = '☑'
            self.account_tree.item(item, values=values)
            session_name = self.account_tree.item(item)['tags'][0]
            self.selected_accounts.append(session_name)
        self.update_stats()
    
    def deselect_all_accounts(self):
        """全不选"""
        self.selected_accounts = []
        for item in self.account_tree.get_children():
            values = list(self.account_tree.item(item)['values'])
            values[0] = '☐'
            self.account_tree.item(item, values=values)
        self.update_stats()
    
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
            
            # 重新加载
            asyncio.run(self.load_accounts())
    
    def start_join(self):
        """开始加群"""
        if not self.selected_accounts:
            messagebox.showwarning("警告", "请先选择账号！")
            return
        
        self.is_running = True
        self.start_button.config(state=DISABLED)
        self.stop_button.config(state=NORMAL)
        
        # 在后台运行
        asyncio.run(self.run_join())
    
    def stop_join(self):
        """停止加群"""
        self.is_running = False
        self.start_button.config(state=NORMAL)
        self.stop_button.config(state=DISABLED)
        self.log("⏸️  已停止", "WARNING")
    
    async def run_join(self):
        """运行加群任务"""
        self.log("=" * 60, "INFO")
        self.log(f"🚀 开始加群！使用 {len(self.selected_accounts)} 个账号", "INFO")
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
        
        total = len(groups)
        success = 0
        failed = 0
        
        # 轮询分配任务
        for idx, link in enumerate(groups):
            if not self.is_running:
                break
            
            # 选择账号（轮询）
            session_name = self.selected_accounts[idx % len(self.selected_accounts)]
            
            # 更新进度
            self.progress['value'] = (idx + 1) / total * 100
            self.progress_label.config(text=f"[{idx + 1}/{total}] 处理中...")
            
            # 加入群
            result = await self.join_group(session_name, link)
            if result:
                success += 1
            else:
                failed += 1
            
            # 智能间隔
            if (idx + 1) % Config.BATCH_SIZE == 0:
                rest = random.randint(Config.BATCH_REST_MIN, Config.BATCH_REST_MAX)
                self.log(f"⏸️  完成一批，休息 {rest} 秒...", "INFO")
                await asyncio.sleep(rest)
            else:
                interval = random.randint(Config.INTERVAL_MIN, Config.INTERVAL_MAX)
                await asyncio.sleep(interval)
        
        # 完成
        self.log("=" * 60, "INFO")
        self.log(f"✅ 加群完成！成功: {success}, 失败: {failed}", "SUCCESS")
        self.log("=" * 60, "INFO")
        
        self.stop_join()
        
        # 重新加载账号统计
        asyncio.run(self.load_accounts())
    
    async def join_group(self, session_name: str, link: str) -> bool:
        """单个账号加入群"""
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
                return False
            
            # 尝试加入
            if parsed['type'] == 'invite':
                await client(ImportChatInviteRequest(parsed['hash']))
            else:
                await client(JoinChannelRequest(parsed['username']))
            
            # 成功
            DataManager.mark_joined(session_name, link)
            self.log(f"✅ [{session_name}] 成功加入: {link}", "SUCCESS")
            return True
        
        except errors.UserAlreadyParticipantError:
            DataManager.mark_joined(session_name, link)
            self.log(f"ℹ️  [{session_name}] 已在群里: {link}", "INFO")
            return True
        
        except Exception as e:
            error_msg = str(e)
            if 'successfully requested to join' in error_msg.lower():
                DataManager.mark_joined(session_name, link)
                self.log(f"✅ [{session_name}] 已申请入群，待审核: {link} ⏳", "SUCCESS")
                return True
            
            self.log(f"❌ [{session_name}] 失败: {link} - {e}", "ERROR")
            return False
        
        finally:
            await client.disconnect()
    
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
