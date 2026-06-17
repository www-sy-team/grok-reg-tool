# -*- coding: utf-8 -*-
"""
DrissionPage 版 Outlook 自动注册机
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
from DrissionPage import Chromium, ChromiumOptions
import tempfile, shutil, random, string, platform

OUTLOOK_POOL = os.environ.get("OUTLOOK_POOL", "/data/sso/outlook_pool.txt")
BROWSER_PROXY = os.environ.get("BROWSER_PROXY", "http://host.docker.internal:10800")
DELAY = int(os.environ.get("OUTLOOK_REG_DELAY", "5"))

if platform.system() == "Linux" and (not os.environ.get("DISPLAY") or os.environ.get("USE_XVFB") == "1"):
    try:
        from pyvirtualdisplay import Display
        _vd = Display(visible=0, size=(1920, 1080))
        _vd.start()
    except Exception:
        pass

def js(page, code):
    return page.run_js(code)

def wait_el(page, sel_js, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if js(page, f"return document.querySelector({sel_js}) ? true : false;"):
            return True
        time.sleep(0.5)
    return False

def fill_input(page, sel_js, val):
    return js(page, f"""
const i = document.querySelector({sel_js});
if (!i) return false;
i.focus();
const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
if (s) s.call(i, '{val}');
i.dispatchEvent(new Event('input', {{bubbles:true}}));
i.dispatchEvent(new Event('change', {{bubbles:true}}));
return true;
""")

def pipe(page, js_query, val):
    """Fill an element with a value using proper quoting."""
    return js(page, """
const i = document.%s;
if (!i) return false;
i.focus();
const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
if (s) s.call(i, '%s');
i.dispatchEvent(new Event('input', {bubbles:true}));
i.dispatchEvent(new Event('change', {bubbles:true}));
return true;
""" % (js_query, val))

def click_next(page):
    return js(page, """
const b = Array.from(document.querySelectorAll('button')).find(x => (x.innerText||'').toLowerCase().trim() === 'next');
if (b) { b.click(); return true; }
return false;
""")

def select_dropdown(page, btn_id, value_text):
    js(page, f"document.getElementById('{btn_id}')?.click()")
    time.sleep(1)
    deadline = time.time() + 10
    while time.time() < deadline:
        r = js(page, f"""
const opt = Array.from(document.querySelectorAll('[role="option"], [role="menuitem"], li')).find(x => (x.innerText||'').toLowerCase().trim() === '{value_text.lower().strip()}');
if (opt) {{ opt.click(); return true; }}
return false;
""")
        if r:
            time.sleep(0.5)
            return True
        time.sleep(0.5)
    return False

def register_one():
    user_dir = tempfile.mkdtemp(prefix='ol_')
    co = ChromiumOptions()
    co.auto_port()
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_proxy(BROWSER_PROXY)
    co.set_timeouts(base=1)
    co.set_user_data_path(user_dir)
    browser = Chromium(co)
    page = browser.new_tab()
    
    try:
        prefix = 'u' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        email = prefix + '@outlook.com'
        pw = 'Pw' + ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        first = random.choice(['John','Emma','Mike','Lisa','Tom','Anna','David','Sophie'])
        last = random.choice(['Smith','Jones','Brown','Taylor','Wilson','Clark'])
        print(f'[*] 注册: {email}')
        
        page.get('https://signup.live.com/signup')
        time.sleep(5)
        
        # Step 1: Email
        pipe(page, "querySelector('input[name=\"email\"]')", email)
        time.sleep(1); click_next(page); time.sleep(5)
        print(f'  ① {page.title}')
        
        # Step 2: Password
        if wait_el(page, '"input[type=\\"password\\"]"'):
            pipe(page, "querySelector('input[type=\"password\"]')", pw)
            time.sleep(1); click_next(page); time.sleep(5)
            print(f'  ② {page.title}')
        
        # Step 3: Birthday
        if 'details' in page.title.lower():
            select_dropdown(page, 'BirthMonthDropdown', 'June')
            select_dropdown(page, 'BirthDayDropdown', '15')
            pipe(page, "querySelector('input[name=\"BirthYear\"]')", '1990')
            time.sleep(1); click_next(page); time.sleep(5)
            print(f'  ③ {page.title}')
        
        # Step 4: Name
        if 'name' in page.title.lower():
            pipe(page, "querySelector('#firstNameInput')", first)
            pipe(page, "querySelector('#lastNameInput')", last)
            time.sleep(1); click_next(page); time.sleep(5)
            print(f'  ④ {page.title}')
        
        # Step 5: PX press-and-hold via CDP
        if 'prove' in page.title.lower() or 'human' in page.title.lower():
            print('  ⚠ PerimeterX - 按住验证 (CDP)...')
            pos_raw = js(page, """
const f = document.querySelector('iframe[src*="hsprotect"]');
if (!f) return '{}';
const r = f.getBoundingClientRect();
return JSON.stringify({cx: r.x + r.width/2, cy: r.y + r.height/2});
""")
            import json as _j
            pos = _j.loads(pos_raw)
            cx, cy = int(pos.get('cx', 0)), int(pos.get('cy', 0))
            if cx and cy:
                print(f'  PX center: ({cx}, {cy})')
                for attempt in range(3):
                    page.run_cdp('Input.dispatchMouseEvent', type='mousePressed', x=cx, y=cy, button='left', clickCount=1)
                    time.sleep(12)
                    page.run_cdp('Input.dispatchMouseEvent', type='mouseReleased', x=cx, y=cy, button='left', clickCount=1)
                    time.sleep(5)
                    if 'outlook.live.com' in page.url or 'account.live.com' in page.url:
                        break
                    print(f'  重试 {attempt+1}/3...')
            page.get_screenshot(path=f'/tmp/px_{prefix}.png', full_page=True)
        
        # Step 6: CAPTCHA / phone verification fallback
        url = page.url
        if 'captcha' in (page.html or '').lower() or 'phone' in (page.html or '').lower():
            print('  ⚠ 验证码/电话验证')
            page.get_screenshot(path=f'/tmp/captcha_{prefix}.png', full_page=True)
        
        # Check result
        if any(d in url for d in ['outlook.live.com', 'login.live.com', 'account.live.com']):
            print(f'  ✅ 注册成功!')
            with open(OUTLOOK_POOL, 'a') as f:
                f.write(f"{email}----{pw}----{first}----{last}\n")
            browser.quit(); shutil.rmtree(user_dir, ignore_errors=True)
            return email, pw
        
        print(f'  URL: {url}')
        page.get_screenshot(path=f'/tmp/ol_end_{prefix}.png', full_page=True)
        browser.quit(); shutil.rmtree(user_dir, ignore_errors=True)
        return None
    except Exception as e:
        print(f'  ! {e}')
        try: page.get_screenshot(path=f'/tmp/ol_err_{prefix}.png', full_page=True)
        except: pass
        browser.quit(); shutil.rmtree(user_dir, ignore_errors=True)
        return None

if __name__ == '__main__':
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(f'[*] Outlook 注册机启动, 目标: {count} 个')
    success = 0
    for i in range(count):
        print(f'\n--- 第 {i+1}/{count} 个 ---')
        r = register_one()
        if r:
            success += 1
        if i < count - 1:
            time.sleep(DELAY)
    print(f'\n完成: 成功 {success}/{count}')
