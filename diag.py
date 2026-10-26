import asyncio
import os
from playwright.async_api import async_playwright

HEADLESS = os.environ.get("HEADLESS", "1") == "1"

async def main():
    os.makedirs("debug", exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=HEADLESS)
        ctx = await b.new_context(locale="en-US")
        page = await ctx.new_page()
        await page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(15000)
        print("HEADLESS:", HEADLESS)
        print("URL:", page.url)
        print("TITLE:", await page.title())
        print("INPUTS:", await page.locator("input").count())
        print("BUTTONS:", await page.locator("button").count())
        print("DIVS:", await page.locator("div").count())
        try:
            print("TEXTO:", (await page.inner_text("body"))[:1500])
        except Exception as e:
            print("TEXTO: error", e)
        html = await page.content()
        print("HTML_LEN:", len(html))
        with open("debug/diag.html", "w", encoding="utf-8") as f:
            f.write(html)
        await page.screenshot(path="debug/diag.png", full_page=True)
        await b.close()

asyncio.run(main())
