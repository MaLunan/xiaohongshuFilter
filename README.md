## ⚠️ 法律免责声明（必读）
1. 本项目仅用于**前端技术学习与学术研究**，禁止用于商业、非法或盈利用途。
2. 仅爬取**小红书Web端公开的内容，不绕过反爬、不破解接口、不获取隐私。
3. 使用本项目产生的一切法律责任由**使用者自行承担**，作者不承担连带责任。
4. 请严格遵守《网络安全法》《个人信息保护法》及小红书用户协议，合规使用。
# xiaohongshuFilter
获取小红书当天关于关键词的信息，比如当天最新的北京的租房帖子、关于xxx二手信息等，仅用于学习爬虫，有封号风险，慎用

```python
"""
小红书搜索结果采集（本地 CLI，Playwright 驱动浏览器）

安装（Homebrew Python 需用虚拟环境，勿直接用系统 pip3）:
  cd 本仓库目录
  python3 -m venv .venv
  source .venv/bin/activate          # Windows: .venv\\Scripts\\activate
  python -m pip install -r requirements-xiaohongshu.txt
  python -m playwright install chromium

用法:
  source .venv/bin/activate
  python xiaohongshu.py "openclaw"
  python xiaohongshu.py "关键词" -o out.json
  python xiaohongshu.py "关键词" --filter-keywords "openclaw,openclaw.ai" --max-posts 20
  python xiaohongshu.py "关键词" --headless   # 需已在本机 profile 里登录过
"""
```
