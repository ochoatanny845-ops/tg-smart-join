# Telegram 智能加群工具

**🎉 现已支持GUI图形界面！**

## 版本选择

### 🖼️ GUI版本（推荐）
- 完整图形界面，操作简单
- 实时日志显示，彩色分类
- 进度条展示，一目了然
- 可视化配置，无需编辑代码
- 使用文件：`smart_join_gui.py`

### 💻 命令行版本
- 适合服务器环境
- 轻量级，资源占用少
- 使用文件：`smart_join.py`

---

## 功能特点

✅ **智能间隔** - 随机30-120秒间隔，避免被封  
✅ **批次休息** - 每5个群休息5-10分钟  
✅ **每日限额** - 默认每天最多加30个群  
✅ **自动跳过** - 已加入的群自动跳过  
✅ **支持多格式** - 公开群/私有群链接都支持  
✅ **完整日志** - 记录所有操作，方便追踪  
✅ **GUI界面** - 图形界面，操作更友好（新增）  

---

## 快速开始（GUI版本）⭐

### 1. 安装依赖

```bash
pip install telethon
```

### 2. 运行程序

```bash
python smart_join_gui.py
```

**默认API配置已内置：**
- API_ID: `2040`
- API_HASH: `b18441a1ff607e10a989891a5462e627`

### 3. 使用步骤

1. **导入Session** - 点击"导入Session"按钮选择 `.session` 文件
2. **添加群链接** - 在"群链接管理"标签页添加群链接
3. **调整配置**（可选） - 在"配置"标签页调整间隔和限额
4. **开始加群** - 返回"加群操作"标签页，点击"▶ 开始加群"

---

## GUI界面预览

### 主界面 - 加群操作
- Session账号选择
- 实时统计信息（总群数/已加入/待加入/今日已加）
- 进度条显示
- 彩色日志输出（信息/成功/警告/错误）

### 群链接管理
- 导入/导出群链接
- 批量编辑
- 实时统计

### 配置
- 普通间隔设置（最小/最大）
- 批次大小
- 批次休息时间
- 每日限额
- 保存配置（持久化）

### 统计
- 已加入群组列表（表格展示）
- 导出CSV
- 清空记录

---

## 快速开始（命令行版本）

### 1. 安装依赖

```bash
pip install telethon
```

### 2. 配置API

**方法1: 修改代码**  
编辑 `smart_join.py` 第15-16行：
```python
API_ID = 你的API_ID
API_HASH = '你的API_HASH'
```

**方法2: 环境变量**
```bash
export API_ID=你的API_ID
export API_HASH=你的API_HASH
```

**获取API_ID和API_HASH:**  
访问 https://my.telegram.org/apps

---

### 3. 准备Session文件

将你的 `.session` 文件放到 `sessions/` 目录下

**如何获取Session文件？**
- 使用 Telethon 登录后会自动生成
- 或从其他工具导出（如之前的JTBot）

---

### 4. 准备群链接

编辑 `groups.txt`，每行一个群链接：

```
https://t.me/example_group
@another_group
https://t.me/+ABC123xyz
https://t.me/joinchat/XXXXX
```

**支持格式：**
- `https://t.me/username` - 公开群
- `@username` - 公开群
- `https://t.me/+XXXXX` - 私有群邀请（新格式）
- `https://t.me/joinchat/XXXXX` - 私有群邀请（旧格式）

---

### 5. 运行

```bash
python smart_join.py
```

**运行流程：**
1. 选择要使用的Session账号
2. 程序自动读取 `groups.txt`
3. 智能加群，自动间隔
4. 完成后显示统计信息

---

## 配置说明

### 智能间隔设置（第20-30行）

```python
INTERVAL_MIN = 30      # 最小间隔30秒
INTERVAL_MAX = 120     # 最大间隔120秒
BATCH_SIZE = 5         # 每批次5个群
BATCH_REST_MIN = 300   # 批次间隔5分钟
BATCH_REST_MAX = 600   # 批次间隔10分钟
DAILY_LIMIT = 30       # 每天最多30个群
```

**建议：**
- 新账号：`DAILY_LIMIT = 20`
- 老账号：`DAILY_LIMIT = 30-50`
- 谨慎操作：减小 `BATCH_SIZE`，增大间隔

---

## 文件结构

```
tg-smart-join/
├── smart_join.py       # 主程序
├── README.md           # 说明文档
├── groups.txt          # 群链接列表（自动生成）
├── joined.json         # 已加入记录（自动生成）
├── smart_join.log      # 运行日志（自动生成）
└── sessions/           # Session文件目录
    └── your_account.session
```

---

## 常见问题

### Q1: 提示"触发限流"怎么办？

**A:** 程序会自动等待，不用担心。如果频繁触发：
- 减小 `DAILY_LIMIT`
- 增大间隔时间
- 暂停一天再继续

---

### Q2: 如何查看加群记录？

**A:** 查看 `joined.json` 文件：
```json
{
  "groups": {
    "https://t.me/example": {
      "title": "示例群组",
      "joined_at": "2026-04-29 16:50:00"
    }
  },
  "daily_count": 10,
  "last_date": "2026-04-29"
}
```

---

### Q3: 加群失败怎么办？

**常见错误：**
- `InviteHashExpiredError` - 邀请链接过期
- `InviteHashInvalidError` - 邀请链接无效
- `ChannelPrivateError` - 群组已私有
- `UserAlreadyParticipantError` - 已经在群里

**解决方法：**
- 检查链接是否有效
- 更新过期的邀请链接
- 手动移除无效链接

---

### Q4: 能同时多个账号加群吗？

**A:** 可以！但**不建议同时运行**多个实例：
1. 先用账号1加完
2. 再用账号2加
3. 避免触发Telegram的批量检测

---

## 安全提示

⚠️ **不要滥用此工具！**
- Telegram有严格的限流机制
- 频繁操作会导致账号受限/封禁
- 建议使用小号，不要用主账号

⚠️ **建议操作：**
- 每天不超过30个群
- 使用随机间隔
- 避免在高峰期（UTC 8-16点）操作
- 定期检查账号状态

---

## 更新日志

### v1.0 (2026-04-29)
- ✅ 初始版本
- ✅ 智能间隔加群
- ✅ 每日限额保护
- ✅ 自动跳过已加入群组
- ✅ 完整日志记录

---

## 许可证

MIT License - 仅供学习交流，请勿用于非法用途
