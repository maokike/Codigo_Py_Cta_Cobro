from playwright.sync_api import sync_playwright

def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # 1. Go to login page
        page.goto("http://127.0.0.1:5000/login")

        # 2. Take screenshot
        page.screenshot(path="jules-scratch/verification/login_page.png")

        browser.close()

if __name__ == "__main__":
    run_verification()
