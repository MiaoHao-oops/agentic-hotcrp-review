"""Read-only browser verification of an existing completed simulation. No model calls."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright
p=argparse.ArgumentParser()
p.add_argument('--conference',required=True)
p.add_argument('--paper',type=int,default=1)
p.add_argument('--url',default='http://127.0.0.1:8765')
a=p.parse_args()
root=Path(__file__).resolve().parents[1]
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(f'{a.url}/?conference={a.conference}')
    page.get_by_role('link',name='查看原生 reviews →').first.wait_for()
    page.screenshot(path=str(root/'data/portal.png'),full_page=True)
    page.get_by_role('link',name='查看原生 reviews →').first.click()
    page.wait_for_load_state('networkidle')
    text=page.locator('body').inner_text()
    assert text.count('SIMULATED REVIEW')>=2, text[:800]
    assert 'Overall merit' in text and 'Comments for authors' in text
    page.screenshot(path=str(root/'data/native-reviews-top.png'))
    page.screenshot(path=str(root/'data/native-reviews.png'),full_page=True)
    page.goto(f'{a.url}/c/{a.conference}/paper/new')
    page.wait_for_load_state('networkidle')
    assert page.locator('[name="title"]').is_visible()
    assert page.get_by_role('button',name='Upload Submission',exact=True).is_visible()
    page.screenshot(path=str(root/'data/native-submission.png'),full_page=True)
    # Fresh session: direct upload links must survive the local auto-login redirect.
    fresh=browser.new_context();newpage=fresh.new_page()
    newpage.goto(f'{a.url}/c/{a.conference}/paper/new')
    newpage.wait_for_load_state('networkidle')
    assert newpage.locator('[name="title"]').is_visible(), newpage.url
    page.set_viewport_size({'width':390,'height':844})
    page.goto(a.url);page.wait_for_timeout(400)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
    assert not errors, errors
    browser.close()
print('Browser checks passed: portal, native reviews, PDF upload form, fresh login, mobile layout, JS errors.')
