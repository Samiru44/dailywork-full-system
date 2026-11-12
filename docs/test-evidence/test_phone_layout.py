"""
Phone-layout sweep: opens every public page and every dashboard tab, for a
visitor and the four seeded roles, at 320, 360 and 390 px wide, and reports any
page that scrolls sideways.

Usage (server running on http://localhost:5000):
    python test_phone_layout.py -
"""
import sys
from playwright.sync_api import sync_playwright
B="http://localhost:5000"
CSS = open(sys.argv[1]).read() if len(sys.argv) > 1 and sys.argv[1] != "-" else ""
ACCTS = [("worker","worker@dailywork.lk","Password@123"),("employer","employer@dailywork.lk","Password@123"),
         ("organization","organization@dailywork.lk","Password@123"),("admin","admin@dailywork.lk","Admin@12345")]
PUBLIC = ["/", "/#/jobs", "/#/about", "/#/features", "/#/pricing", "/#/contact", "/#/login", "/#/register"]
bad = []
checked = 0
def over(pg):
    global checked
    checked += 1
    return pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
with sync_playwright() as p:
    b = p.chromium.launch()
    for w in (320, 360, 390):
        ctx = b.new_context(viewport={"width": w, "height": 800}); pg = ctx.new_page()
        for path in PUBLIC:
            pg.goto(B+path); pg.wait_for_timeout(700)
            if CSS: pg.add_style_tag(content=CSS)
            o = over(pg)
            if o > 1: bad.append((w, "visitor", path, o))
        ctx.close()
        for role, email, pw in ACCTS:
            ctx = b.new_context(viewport={"width": w, "height": 800}); pg = ctx.new_page()
            pg.goto(B+"/#/login"); pg.wait_for_timeout(600)
            pg.fill('input[type=email]', email); pg.fill('input[type=password]', pw)
            pg.click('button[type=submit]'); pg.wait_for_timeout(1300)
            pg.goto(B+"/#/dashboard"); pg.wait_for_timeout(1000)
            if CSS: pg.add_style_tag(content=CSS)
            tabs = pg.locator(".dash-side a").all_inner_texts()
            for i, t in enumerate(tabs):
                href = pg.locator(".dash-side a").nth(i).get_attribute("href") or ""
                if href.startswith("#/") and href not in ("#/dashboard",): 
                    continue  # links that leave the dashboard (Browse Jobs, Plans, Admin Panel)
                pg.locator(".dash-side a").nth(i).click(); pg.wait_for_timeout(700)
                o = over(pg)
                if o > 1: bad.append((w, role, t.split("\n")[0], o))
            if role == "admin":
                pg.goto(B+"/#/admin"); pg.wait_for_timeout(1000)
                if CSS: pg.add_style_tag(content=CSS)
                o = over(pg)
                if o > 1: bad.append((w, role, "/admin", o))
            ctx.close()
    b.close()
print("PAGE VIEWS CHECKED:", checked)
print("PAGES WITH SIDEWAYS SCROLL:", len(bad))
for x in bad: print("  ", x)
