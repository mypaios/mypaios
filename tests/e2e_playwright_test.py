import sys
import asyncio
from playwright.async_api import async_playwright

async def main():
    print("Starting E2E Playwright test...")
    sys.stdout.flush()
    
    async with async_playwright() as p:
        try:
            print("Launching headless Chromium...")
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            url = "http://127.0.0.1:7860"
            print(f"Navigating to {url}...")
            await page.goto(url)
            await page.wait_for_timeout(3000)
            
            print(f"Loaded page. Current URL: {page.url}")
            sys.stdout.flush()
            
            # Click model picker
            print("Clicking model picker button...")
            picker_btn = page.locator("#model-picker-btn")
            await picker_btn.click()
            await page.wait_for_timeout(1000)
            
            # Wait for search box to be visible
            print("Searching for model 'qwen2.5-coder:32b'...")
            search_box = page.locator("#model-picker-search")
            await search_box.fill("qwen2.5-coder:32b")
            await page.wait_for_timeout(1000)
            
            # Locate first matching item in list
            item = page.locator("#model-picker-list .model-switch-item").first
            if await item.is_visible():
                print("Clicking model-switch item...")
                await item.click()
                await page.wait_for_timeout(1000)
            else:
                print("Error: qwen2.5-coder:32b item not visible in list!")
                sys.exit(1)
            
            # Enter message
            print("Entering message prompt...")
            message_box = page.locator("#message").first
            await message_box.fill("Sort an array in python in one line.")
            await page.wait_for_timeout(500)
            
            # Click send button
            print("Clicking send button...")
            send_btn = page.locator(".send-btn").first
            await send_btn.click()
            
            print("Waiting for response to stream...")
            # Wait for message bubble to appear
            ai_body = page.locator(".msg-ai .body").last
            # Wait up to 30s for the message body to be populated
            await ai_body.wait_for(state="visible", timeout=30000)
            
            # Wait a few seconds for streaming to complete
            for i in range(10):
                await page.wait_for_timeout(1000)
                text = await ai_body.text_content()
                print(f"Streaming [{i}/10]: {len(text)} chars received")
                sys.stdout.flush()
            
            final_text = await ai_body.text_content()
            print("\nFinal response received:")
            print("-" * 60)
            print(final_text)
            print("-" * 60)
            sys.stdout.flush()
            
            if len(final_text.strip()) > 10:
                print("E2E Test: SUCCESS!")
            else:
                print("E2E Test: FAILED (Response was too short)")
                sys.exit(1)
                
            await browser.close()
        except Exception as e:
            print("E2E Test: ERROR occurred:", e)
            sys.stdout.flush()
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
