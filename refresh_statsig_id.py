"""Refresh x-statsig-id via CDP script injection + SSO cookie."""
import time, subprocess, sys
from DrissionPage.common import Keys
from DrissionPage import Chromium, ChromiumOptions
from pyvirtualdisplay import Display

disp = Display(visible=0, size=(1920, 1080))
disp.start()

co = ChromiumOptions()
co.auto_port()
co.set_argument("--no-sandbox")
co.set_argument("--disable-gpu")
co.set_argument("--disable-dev-shm-usage")
co.set_argument("--disable-software-rasterizer")
co.add_extension("/app/register/turnstilePatch")

browser = Chromium(co)
tab = browser.latest_tab

tab.run_cdp("Page.addScriptToEvaluateOnNewDocument", source="""
window.__statsig = null;
const origFetch = window.fetch.bind(window);
window.fetch = async function(url, opts) {
    const u = typeof url === 'string' ? url : (url?.url || url?.href || '');
    if (u.includes('conversations/new')) {
        const h = opts?.headers || {};
        const v = h['x-statsig-id'] || h['X-Statsig-Id'];
        if (v) window.__statsig = v;
    }
    return origFetch(url, opts);
};
""")

SSO = ""
SSO_FILE = "/app/register/sso_refresh_token.txt"
try:
    with open(SSO_FILE) as f:
        SSO = f.read().strip()
except:
    sys.stderr.write("No SSO token file, trying anonymous\n")

STATSIG_ID = None
tab.get("https://grok.com/")
time.sleep(5)

if SSO:
    tab.run_js(f'document.cookie = "sso={SSO}; path=/; domain=.grok.com";')
    tab.run_js(f'document.cookie = "sso-rw={SSO}; path=/; domain=.grok.com";')
    time.sleep(2)
    tab.get("https://grok.com/")
    time.sleep(10)

try:
    ta = tab.ele("tag:textarea", timeout=5)
    if ta:
        ta.click()
        time.sleep(1)
        ta.input("hello")
        time.sleep(2)
        ta.input(Keys.ENTER)
        time.sleep(15)
except Exception as e:
    sys.stderr.write(f"UI: {e}\n")

STATSIG_ID = tab.run_js("return window.__statsig;")

if STATSIG_ID:
    print(f"OK {STATSIG_ID}")
    with open("/tmp/current_statsig_id.txt", "w") as f:
        f.write(STATSIG_ID)
    cmd = (
        'docker exec -i grok2api python3 -c "'
        "import tomllib, tomli_w; "
        "c=tomllib.load(open('/app/data/config.toml','rb')); "
        "c['proxy']=c.get('proxy',{}); "
        f"c['proxy']['statsig_id']='{STATSIG_ID}'; "
        "tomli_w.dump(c,open('/app/data/config.toml','wb')); "
        "print('ok')"
        '"'
    )
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode == 0:
        subprocess.run("docker restart grok2api 2>&1", shell=True)
        print("restarted")
else:
    print("FAIL (old value kept)")

browser.quit()
disp.stop()
