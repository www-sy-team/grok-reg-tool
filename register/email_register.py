
from __future__ import annotations

import json
import os
import random
import re
import string
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================================
# 自建邮件服务配置（兼容 dreamhunter2333/cloudflare_temp_email / vmail）
# ============================================================

_config_path = Path(__file__).parent / "config.json"
_conf: Dict[str, Any] = {}
if _config_path.exists():
    with _config_path.open("r", encoding="utf-8") as _f:
        _conf = json.load(_f)

MAIL_API_BASE = str(_conf.get("mail_api_base", "")).rstrip("/")
MAIL_ADMIN_AUTH = str(_conf.get("mail_admin_auth", ""))
MAIL_DOMAIN = str(_conf.get("mail_domain", ""))
MAIL_CUSTOM_AUTH = str(_conf.get("mail_custom_auth", os.environ.get("MAIL_CUSTOM_AUTH", "")))
PROXY = str(_conf.get("proxy", ""))

# ============================================================
# mail.tm 后端（当 MAILTM=1 时启用）
# ============================================================

_MAILTM_ENABLED = os.environ.get("MAILTM") in ("1", "true", "yes")

def _mailtm_no_proxy():
    return {"http": "", "https": ""}

_MAILTM_DOMAIN = "web-library.net"
_MAILTM_API = "https://api.mail.tm"


def _mailtm_create_account() -> Tuple[str, str, str]:
    """在 mail.tm 上创建一个新地址，返回 (email, password, jwt)"""
    import uuid
    local = "u" + uuid.uuid4().hex[:10]
    email = f"{local}@{_MAILTM_DOMAIN}"
    password = "P" + uuid.uuid4().hex[:12]

    resp = requests.post(
        f"{_MAILTM_API}/accounts",
        json={"address": email, "password": password},
        headers={"Content-Type": "application/json"},
        proxies=_mailtm_no_proxy(),
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        raise Exception(f"mail.tm 创建账号失败: HTTP {resp.status_code} {resp.text[:200]}")

    # 登录获取 JWT
    resp2 = requests.post(
        f"{_MAILTM_API}/token",
        json={"address": email, "password": password},
        headers={"Content-Type": "application/json"},
        proxies=_mailtm_no_proxy(),
        timeout=15,
    )
    if resp2.status_code != 200:
        raise Exception(f"mail.tm 登录失败: HTTP {resp2.status_code} {resp2.text[:200]}")

    jwt = resp2.json().get("token") or resp2.json().get("id", "")
    print(f"[*] 邮箱创建成功: {email}")
    return email, password, jwt


def _mailtm_fetch_emails(jwt: str) -> List[Dict[str, Any]]:
    """获取 mail.tm 邮件列表"""
    try:
        resp = requests.get(
            f"{_MAILTM_API}/messages?page=1",
            headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
            proxies=_mailtm_no_proxy(),
            timeout=10,
        )
        if resp.status_code == 200:
            members = resp.json().get("hydra:member", [])
            results = []
            for m in members:
                mid = m.get("id", "")
                detail = requests.get(
                    f"{_MAILTM_API}/messages/{mid}",
                    headers={"Authorization": f"Bearer {jwt}"},
                    proxies=_mailtm_no_proxy(),
                    timeout=10,
                ).json()
                html = detail.get("html", [""])[0] if detail.get("html") else ""
                text = detail.get("text", "")
                subject = detail.get("subject", "")
                results.append({
                    "id": mid,
                    "subject": subject,
                    "html": html,
                    "text": text,
                    "raw": text or html,
                })
            return results
    except Exception:
        pass
    return []


# ============================================================
# 适配层：为 DrissionPage_example.py 提供简单接口
# ============================================================


def get_email_and_token() -> Tuple[Optional[str], Optional[str]]:
    """
    创建一个新地址，返回 (email, jwt)。
    jwt 用于后续轮询邮件。
    当 MAILTM=1 时使用 mail.tm，否则使用自建邮件服务。
    """
    if _MAILTM_ENABLED:
        email, _password, jwt = _mailtm_create_account()
        if email and jwt:
            return email, jwt
        return None, None
    email, _password, jwt = create_temp_email()
    if email and jwt:
        return email, jwt
    return None, None


def get_oai_code(dev_token: str, email: str, timeout: int = 30) -> Optional[str]:
    """
    轮询邮箱获取 Grok/x.ai 发来的 OTP 验证码。
    返回去掉连字符后的字符串（如 "MM0SF3"），失败返回 None。
    """
    code = wait_for_verification_code(jwt=dev_token, timeout=timeout)
    if code:
        code = code.replace("-", "")
    return code


# ============================================================
# 核心：与 vmail (https://github.com/...) 后端交互
# ============================================================


def _create_session():
    """优先 curl_cffi 走 chrome131 指纹，避免 Cloudflare 拦截"""
    if curl_requests:
        session = curl_requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        if PROXY:
            session.proxies = {"http": PROXY, "https": PROXY}
        return session, True

    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
    })
    if PROXY:
        s.proxies = {"http": PROXY, "https": PROXY}
    return s, False


def _do_request(session, use_cffi, method, url, **kwargs):
    if use_cffi:
        kwargs.setdefault("impersonate", "chrome131")
    return getattr(session, method)(url, **kwargs)


def _generate_local_part(min_len=8, max_len=13) -> str:
    chars = string.ascii_lowercase + string.digits
    length = random.randint(min_len, max_len)
    # 首字符必须是字母，避免某些校验拒绝纯数字开头
    return random.choice(string.ascii_lowercase) + "".join(
        random.choice(chars) for _ in range(length - 1)
    )


def create_temp_email() -> Tuple[str, str, str]:
    """
    通过 admin 接口创建一个新地址。
    后端返回 {jwt, address, password}，jwt 即用于读邮件的 Bearer。
    """
    if not MAIL_ADMIN_AUTH:
        raise Exception("mail_admin_auth 未设置，无法创建邮箱地址")

    headers = {"x-admin-auth": MAIL_ADMIN_AUTH}
    if MAIL_CUSTOM_AUTH:
        headers["x-custom-auth"] = MAIL_CUSTOM_AUTH
    session, use_cffi = _create_session()

    last_err = ""
    for _ in range(5):
        local = _generate_local_part()
        try:
            res = _do_request(
                session, use_cffi, "post",
                f"{MAIL_API_BASE}/admin/new_address",
                json={"name": local, "domain": MAIL_DOMAIN, "enablePrefix": False},
                headers=headers,
                timeout=15,
            )
            if res.status_code in (200, 201):
                data = res.json()
                jwt = data.get("jwt")
                address = data.get("address") or f"{local}@{MAIL_DOMAIN}"
                password = data.get("password", "")
                if jwt and address:
                    print(f"[*] 邮箱创建成功: {address}")
                    return address, password, jwt
                last_err = f"响应缺少 jwt/address: {data}"
            else:
                last_err = f"HTTP {res.status_code}: {res.text[:200]}"
                # 地址冲突就换个 local 再试
                if res.status_code in (400, 409):
                    continue
                break
        except Exception as e:
            last_err = str(e)

    raise Exception(f"创建邮箱失败: {last_err}")


def fetch_emails(jwt: str, limit: int = 20) -> List[Dict[str, Any]]:
    """获取邮件列表"""
    if _MAILTM_ENABLED:
        return _mailtm_fetch_emails(jwt)
    try:
        headers = {"Authorization": f"Bearer {jwt}"}
        if MAIL_CUSTOM_AUTH:
            headers["x-custom-auth"] = MAIL_CUSTOM_AUTH
        session, use_cffi = _create_session()
        res = _do_request(
            session, use_cffi, "get",
            f"{MAIL_API_BASE}/api/mails",
            params={"limit": limit, "offset": 0},
            headers=headers,
            timeout=15,
        )
        if res.status_code == 200:
            data = res.json()
            return data.get("results") or []
    except Exception:
        pass
    return []


def fetch_email_detail(jwt: str, msg_id: Any) -> Optional[Dict]:
    """获取单封邮件详情（含正文）"""
    if _MAILTM_ENABLED:
        return None  # _mailtm_fetch_emails already gets full detail
    try:
        headers = {"Authorization": f"Bearer {jwt}"}
        if MAIL_CUSTOM_AUTH:
            headers["x-custom-auth"] = MAIL_CUSTOM_AUTH
        session, use_cffi = _create_session()
        res = _do_request(
            session, use_cffi, "get",
            f"{MAIL_API_BASE}/api/mail/{msg_id}",
            headers=headers,
            timeout=15,
        )
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None


def wait_for_verification_code(jwt: str, timeout: int = 120) -> Optional[str]:
    """轮询等待验证码邮件"""
    start = time.time()
    seen_ids = set()

    try:
        poll_interval = max(0.5, float(_conf.get("mail_poll_interval", 1)))
    except (TypeError, ValueError):
        poll_interval = 1

    while time.time() - start < timeout:
        messages = fetch_emails(jwt)
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            msg_id = msg.get("id")
            if msg_id is None or msg_id in seen_ids:
                continue
            seen_ids.add(msg_id)

            # 列表接口通常已带正文；不够时再请求详情。
            content = (
                msg.get("raw")
                or msg.get("text")
                or msg.get("html")
                or msg.get("body")
                or ""
            )
            if not content:
                detail = fetch_email_detail(jwt, msg_id)
                if detail:
                    content = (
                        detail.get("raw")
                        or detail.get("text")
                        or detail.get("html")
                        or detail.get("body")
                        or ""
                    )

            # 把 subject 也并进来，方便 6 位数字模式匹配
            subject = msg.get("subject") or ""
            if subject:
                content = f"Subject: {subject}\n{content}"

            code = extract_verification_code(content)
            if code:
                print(f"[*] 提取到验证码: {code}")
                return code
        time.sleep(poll_interval)
    return None


# ============================================================
# Outlook 邮箱支持（浏览器登录方式）
# ============================================================

def read_outlook_code_via_browser(
    page_manager,
    email: str,
    password: str,
    timeout: int = 120,
) -> Optional[str]:
    """
    在同一个浏览器中打开 Outlook 收件箱，读取 x.ai 验证码邮件。
    page_manager 是 DrissionPage_example 的模块级工具函数提供者。
    返回验证码，失败返回 None。
    """
    import time
    import re

    try:
        open_tab = page_manager.get_page().run_js("() => window.open('https://outlook.live.com')")
    except Exception:
        return None

    time.sleep(3)

    try:
        tabs = page_manager.get_browser().get_tabs()
        outlook_tab = tabs[-1]
        outlook_tab.set.window.max()
    except Exception:
        return None

    deadline = time.time() + timeout
    logged_in = False

    # Step 1: click "Sign in" button
    while time.time() < deadline and not logged_in:
        try:
            clicked = outlook_tab.run_js(r"""
const btns = Array.from(document.querySelectorAll('a, button, [role="button"]'));
const signin = btns.find(b => {
    const t = (b.innerText || b.textContent || '').toLowerCase().replace(/\s+/g, '');
    return t.includes('signin') || t.includes('sign-in') || t.includes('登录') || t.includes('サインイン');
});
if (signin) { signin.click(); return true; }
return false;
""")
            if clicked:
                time.sleep(2)
                break
            time.sleep(0.5)
        except Exception:
            time.sleep(1)

    # Step 2: fill email
    while time.time() < deadline and not logged_in:
        try:
            filled = outlook_tab.run_js(f"""
const input = document.querySelector('input[type="email"]');
if (!input) return 'not-ready';
input.value = '{email}';
input.dispatchEvent(new Event('input', {{bubbles:true}}));
input.dispatchEvent(new Event('change', {{bubbles:true}}));

const next = Array.from(document.querySelectorAll('input[type="submit"], button')).find(b => {{
    const t = (b.innerText || b.value || '').toLowerCase();
    return t.includes('next') || t.includes('次へ') || t.includes('下一步');
}});
if (next) {{ next.click(); return 'clicked'; }}
return 'filled';
""")
            if filled == 'clicked':
                time.sleep(2)
                break
            time.sleep(0.5)
        except Exception:
            time.sleep(1)

    # Step 3: fill password
    while time.time() < deadline and not logged_in:
        try:
            filled = outlook_tab.run_js(f"""
const input = document.querySelector('input[type="password"]');
if (!input) return 'not-ready';
input.value = '{password}';
input.dispatchEvent(new Event('input', {{bubbles:true}}));
input.dispatchEvent(new Event('change', {{bubbles:true}}));

const signin = Array.from(document.querySelectorAll('input[type="submit"], button')).find(b => {{
    const t = (b.innerText || b.value || '').toLowerCase();
    return t.includes('signin') || t.includes('sign-in') || t.includes('登录') || t.includes('サインイン');
}});
if (signin) {{ signin.click(); return 'clicked'; }}
return 'filled';
""")
            if filled == 'clicked':
                time.sleep(5)
                logged_in = True
                break
            if filled == 'not-ready':
                time.sleep(1)
                continue
            time.sleep(0.5)
        except Exception:
            time.sleep(1)

    if not logged_in:
        print("[!] Outlook 登录失败或超时")
        try:
            outlook_tab.close()
        except Exception:
            pass
        return None

    # Step 4: navigate to inbox and wait for x.ai email
    print("[*] Outlook 登录成功，等待 x.ai 验证码邮件...")
    time.sleep(3)

    code = None
    while time.time() < deadline:
        try:
            found = outlook_tab.run_js(r"""
// Navigate to focused inbox
const inboxLinks = Array.from(document.querySelectorAll('a, span, div')).filter(el => {
    const t = (el.innerText || el.textContent || '').toLowerCase().replace(/\s+/g, '');
    return t.includes('inbox') || t.includes('受信トレイ') || t.includes('收件箱');
});
if (inboxLinks.length > 0) {
    inboxLinks[0].click();
    return 'navigating';
}

// Check current page for emails - look for x.ai
const emails = Array.from(document.querySelectorAll('[role="listitem"], [role="option"], .msgItem, .emailItem, tr, li')).filter(el => {
    const t = (el.innerText || el.textContent || '').toLowerCase();
    return t.includes('x.ai') || t.includes('grok') || t.includes('verify') || t.includes('confirm') || t.includes('確認');
});
if (emails.length > 0) {
    emails[0].click();
    return 'clicked';
}

// Already on email detail page - extract code
const content = document.body.innerText || document.body.textContent || '';
const m = content.match(/([A-Z0-9]{3}-[A-Z0-9]{3})/);
if (m) return 'code:' + m[1];
const m2 = content.match(/\b(\d{6})\b/);
if (m2 && m2[1] !== '177010') return 'code:' + m2[1];

return 'waiting';
""")
            if found and found.startswith('code:'):
                code = found.split(':')[1]
                print(f"[*] Outlook 验证码: {code}")
                break
            if found == 'clicked':
                time.sleep(2)
                continue
        except Exception:
            pass
        time.sleep(2)

    try:
        outlook_tab.close()
    except Exception:
        pass

    # Switch back to main tab
    try:
        tabs = page_manager.get_browser().get_tabs()
        page_manager.set_page(tabs[0] if tabs else page_manager.get_page())
    except Exception:
        pass

    return code


# ============================================================
# 易久 API 取件（Outlook 邮箱）
# ============================================================

OUTLOOK_API_BASE = "https://api.bujidian.com"

def get_oai_code_from_outlook_api(email: str, password: str, timeout: int = 180) -> Optional[str]:
    """
    通过易久 API 轮询 Outlook 收件箱，等待 x.ai 验证码邮件。
    返回验证码（格式 XXX-XXX），超时返回 None。
    API 的 sender 参数是精确匹配，故不用 sender 参数，
    在返回的 mail 中自行检查 sender 是否来自 x.ai。
    """
    import requests, time, re

    deadline = time.time() + timeout
    print(f"[*] Outlook API 轮询: {email}")

    while time.time() < deadline:
        try:
            r = requests.get(
                f"{OUTLOOK_API_BASE}/getMailInfo",
                params={
                    "name": email,
                    "pwd": password,
                },
                timeout=15,
            )
            data = r.json()
        except Exception as e:
            print(f"  [!] API 请求异常: {e}")
            time.sleep(5)
            continue

        if data.get("status") != 1:
            print(f"  [.] 暂无新邮件，等待中...")
            time.sleep(5)
            continue

        msg = data.get("message", {})
        subject = msg.get("subject", "") or ""
        content = msg.get("content", "") or ""
        sender = msg.get("sender", "") or ""

        # 只处理 x.ai 发来的邮件
        if "x.ai" not in sender.lower() and "x.ai" not in subject.lower():
            print(f"  [.] 非 x.ai 邮件 ({sender})，跳过...")
            time.sleep(5)
            continue

        print(f"  [*] 收到 x.ai 邮件: {subject[:60]}")

        # Try to extract the verification code from content
        # x.ai formats: XXX-XXX (3 uppercase letters, dash, 3 uppercase letters)
        for text in [content, subject]:
            m = re.search(r'([A-Z0-9]{3}-[A-Z0-9]{3})', text)
            if m:
                code = m.group(1)
                print(f"  [*] 验证码: {code}")
                return code
            # Fallback: 6-digit code
            m2 = re.search(r'\b(\d{6})\b', text)
            if m2:
                code = m2.group(1)
                print(f"  [*] 验证码(数字): {code}")
                return code

        print(f"  [.] 未找到验证码格式，继续等待...")
        time.sleep(5)

    print(f"  [!] 超时，未收到验证码")
    return None


def extract_verification_code(content: str) -> Optional[str]:
    """
    从邮件内容提取验证码。
    Grok/x.ai 格式：MM0-SF3（3位-3位字母数字混合）或 6 位纯数字。
    """
    if not content:
        return None

    # 模式 1: Grok 格式 XXX-XXX
    m = re.search(r"(?<![A-Z0-9-])([A-Z0-9]{3}-[A-Z0-9]{3})(?![A-Z0-9-])", content)
    if m:
        return m.group(1)

    # 模式 2: 带标签的验证码
    m = re.search(r"(?:verification code|验证码|your code)[:\s]*[<>\s]*([A-Z0-9]{3}-[A-Z0-9]{3})\b", content, re.IGNORECASE)
    if m:
        return m.group(1)

    # 模式 3: HTML 样式包裹
    m = re.search(r"background-color:\s*#F3F3F3[^>]*>[\s\S]*?([A-Z0-9]{3}-[A-Z0-9]{3})[\s\S]*?</p>", content)
    if m:
        return m.group(1)

    # 模式 4: Subject 行 6 位数字
    m = re.search(r"Subject:.*?(\d{6})", content)
    if m and m.group(1) != "177010":
        return m.group(1)

    # 模式 5: HTML 标签内 6 位数字
    for code in re.findall(r">\s*(\d{6})\s*<", content):
        if code != "177010":
            return code

    # 模式 6: 独立 6 位数字
    for code in re.findall(r"(?<![&#\d])(\d{6})(?![&#\d])", content):
        if code != "177010":
            return code

    return None
