#!/usr/bin/env python3
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

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_USER_DATA = SCRIPT_DIR / "xhs_playwright_profile"


def check_login(page) -> bool:
    js = """() => {
        const loginBtn = document.querySelector('a[href*="/login"]');
        const userAvatar = document.querySelector('.avatar, .user-avatar');
        if (userAvatar) return true;
        if (loginBtn) return false;
        return true;
    }"""
    try:
        return bool(page.evaluate(js))
    except Exception:
        return True


def wait_for_login(page, timeout: int) -> bool:
    if timeout <= 0:
        return False
    print(f"等待登录（最多 {timeout // 60} 分钟），请在浏览器窗口完成扫码…")
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(3)
        if check_login(page):
            print("✅ 已登录")
            return True
        print("  仍在等待…")
    return False


def scrape_posts(page, keyword: str, max_posts: int) -> list[dict]:
    ts = int(time.time())
    q = quote(keyword, safe="")
    search_url = (
        f"https://www.xiaohongshu.com/search_result?keyword={q}&_t={ts}"
    )
    print(f"🌐 {search_url}")
    page.goto(search_url, wait_until="domcontentloaded", timeout=90_000)
    time.sleep(5)
    print("⏳ 等待页面稳定…")
    time.sleep(3)

    search_btn_js = """() => {
        const searchIcons = document.querySelectorAll('#search-icon, .search-icon, [class*="search"] svg, [class*="search-btn"]');
        for (let el of searchIcons) {
            const rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                el.click();
                return 'clicked_search_icon';
            }
        }
        const input = document.querySelector('input[placeholder*="搜索"]');
        if (input) {
            input.focus();
            input.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));
            input.dispatchEvent(new KeyboardEvent('keypress', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));
            input.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));
            return 'pressed_enter';
        }
        return 'search_not_found';
    }"""
    r = page.evaluate(search_btn_js)
    print("🔍 触发搜索:", r)
    time.sleep(5)

    filter_js = """() => {
        const filterEl = document.querySelector('.filter');
        if (filterEl) {
            filterEl.click();
            return 'clicked_filter';
        }
        return 'filter_not_found';
    }"""
    print("筛选按钮:", page.evaluate(filter_js))
    time.sleep(2)

    latest_js = """() => {
        const tags = document.querySelectorAll('.filter-panel .tags');
        for (let t of tags) {
            if (t.textContent?.trim() === '最新') {
                const style = window.getComputedStyle(t);
                if (parseFloat(style.opacity) > 0.5 || !t.getAttribute('aria-hidden')) {
                    t.click();
                    return 'clicked_latest';
                }
            }
        }
        return 'latest_not_found';
    }"""
    print("最新排序:", page.evaluate(latest_js))
    time.sleep(8)

    js_extract = f"""() => {{
        const maxN = {int(max_posts)};
        const posts = [];
        document.querySelectorAll('section.note-item').forEach((item, idx) => {{
            if (idx >= maxN) return;
            const links = Array.from(item.querySelectorAll('a'));
            let title = '';
            let titleHref = '';
            let author = '';
            let pubDate = '';
            let likes = '0';
            for (let link of links) {{
                const text = link.textContent?.trim() || '';
                const href = link.href || '';
                if (text.length > 5 && !href.includes('/user/')) {{
                    if (!/\\d{{2}}-\\d{{2}}|\\d{{4}}-\\d{{2}}|天前|小时前/.test(text)) {{
                        title = text;
                        titleHref = href;
                        break;
                    }}
                }}
            }}
            for (let link of links) {{
                const text = link.textContent?.trim() || '';
                const href = link.href || '';
                if (href.includes('/user/profile/') && text.length > 0) {{
                    const datePatterns = /(\\d{{2}}-\\d{{2}}|\\d{{4}}-\\d{{2}}-\\d{{2}}|\\d+天前|\\d+小时前|今天|刚刚|\\d+月\\d+日)/;
                    const match = text.match(datePatterns);
                    if (match) {{
                        author = text.substring(0, text.indexOf(match[1])).trim();
                        pubDate = match[1];
                    }} else {{
                        author = text;
                    }}
                    break;
                }}
            }}
            const textLines = item.innerText?.split('\\n') || [];
            for (let line of textLines) {{
                if (/^\\d+$/.test(line.trim())) {{
                    likes = line.trim();
                    break;
                }}
            }}
            if (title && title.length > 3) {{
                posts.push({{title, author, pubDate, likes, link: titleHref}});
            }}
        }});
        return {{ count: posts.length, data: posts }};
    }}"""

    data = page.evaluate(js_extract)
    if not isinstance(data, dict):
        return []
    return list(data.get("data") or [])


def apply_relevance_filter(
    posts: list[dict], keywords: list[str]
) -> list[dict]:
    if not keywords:
        return posts
    out = []
    for p in posts:
        title = p.get("title", "") or ""
        author = p.get("author", "") or ""
        combined = title + author
        if any(k.strip() in combined for k in keywords if k.strip()):
            out.append(p)
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="小红书搜索页笔记列表采集（Playwright / Chromium）"
    )
    p.add_argument(
        "keyword",
        nargs="?",
        default=os.environ.get("XHS_KEYWORD", "openclaw"),
        help="搜索关键词（环境变量 XHS_KEYWORD）",
    )
    p.add_argument(
        "-o",
        "--output",
        help="JSON 输出路径；默认 stdout",
    )
    p.add_argument(
        "--max-posts",
        type=int,
        default=30,
        help="最多解析笔记条数（默认 30）",
    )
    p.add_argument(
        "--filter-keywords",
        metavar="K1,K2,...",
        help="可选：标题或作者含任一子串才保留",
    )
    p.add_argument(
        "--user-data",
        type=Path,
        default=Path(
            os.environ.get("XHS_USER_DATA", str(DEFAULT_USER_DATA))
        ),
        help=f"持久化用户目录（登录态），默认 {DEFAULT_USER_DATA}",
    )
    p.add_argument(
        "--login-timeout",
        type=int,
        default=300,
        help="未登录时等待秒数（默认 300；0 表示不等待，未登录则退出码 3）",
    )
    p.add_argument(
        "--headless",
        action="store_true",
        help="无头模式（需已在该 user-data 下登录过）",
    )
    p.add_argument(
        "--channel",
        default=os.environ.get("XHS_PLAYWRIGHT_CHANNEL", ""),
        help="可选：系统 Chrome，例如 chrome / msedge（需本机已安装）",
    )
    return p.parse_args()


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "错误: 当前 Python 环境里没有 playwright。\n"
            "若系统 pip 报 externally-managed-environment，请在本目录用虚拟环境：\n"
            "  python3 -m venv .venv && source .venv/bin/activate\n"
            "  python -m pip install playwright && python -m playwright install chromium\n"
            "然后仍用该环境运行: python xiaohongshu.py …",
            file=sys.stderr,
        )
        return 1

    args = parse_args()
    user_data = args.user_data.expanduser().resolve()
    user_data.mkdir(parents=True, exist_ok=True)

    posts: list[dict] = []

    print("=== Playwright 启动（持久化 profile）===")
    print(f"用户目录: {user_data}")

    with sync_playwright() as pw:
        launch_kw: dict = {
            "user_data_dir": str(user_data),
            "headless": args.headless,
            "viewport": {"width": 1280, "height": 900},
            "locale": "zh-CN",
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if args.channel:
            launch_kw["channel"] = args.channel

        context = pw.chromium.launch_persistent_context(**launch_kw)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(
                "https://www.xiaohongshu.com",
                wait_until="domcontentloaded",
                timeout=90_000,
            )
            time.sleep(2)

            if not check_login(page):
                print("⚠️ 需要登录")
                if args.login_timeout <= 0 or not wait_for_login(
                    page, args.login_timeout
                ):
                    print("错误: 未在时限内完成登录", file=sys.stderr)
                    return 3

            posts = scrape_posts(page, args.keyword, args.max_posts)
        finally:
            context.close()

    filter_list: list[str] = []
    if args.filter_keywords:
        filter_list = [
            x.strip() for x in args.filter_keywords.split(",") if x.strip()
        ]
    filtered = apply_relevance_filter(posts, filter_list)
    if filter_list and len(filtered) < len(posts):
        print(
            f"相关性过滤: {len(posts)} → {len(filtered)} 条 "
            f"（关键词: {filter_list}）"
        )

    payload = {
        "keyword": args.keyword,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(filtered),
        "posts": filtered,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"✅ 已写入 {out_path}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
