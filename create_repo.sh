#!/bin/bash
# GitHub 仓库创建和推送脚本

# 仓库信息
REPO_NAME="tg-smart-join"
REPO_DESC="Telegram智能加群工具 - 支持批量加群，智能间隔，每日限额保护"
REPO_PRIVATE="false"  # 改为 true 则创建私有仓库

echo "正在创建GitHub仓库..."

# 方法1: 使用GitHub CLI (推荐)
# 需要先安装: winget install GitHub.cli
gh repo create $REPO_NAME --public --description "$REPO_DESC" --source=. --remote=origin --push

# 方法2: 使用GitHub API (需要Personal Access Token)
# 1. 访问 https://github.com/settings/tokens
# 2. 生成新token，勾选 repo 权限
# 3. 复制token替换下面的 YOUR_GITHUB_TOKEN

# GITHUB_TOKEN="YOUR_GITHUB_TOKEN"
# GITHUB_USERNAME="luoshen"  # 替换为你的GitHub用户名
# 
# curl -H "Authorization: token $GITHUB_TOKEN" \
#      -d "{\"name\":\"$REPO_NAME\",\"description\":\"$REPO_DESC\",\"private\":$REPO_PRIVATE}" \
#      https://api.github.com/user/repos
# 
# git remote add origin https://github.com/$GITHUB_USERNAME/$REPO_NAME.git
# git branch -M main
# git push -u origin main

echo "完成！"
