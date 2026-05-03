import os
import asyncio
import base64
from dotenv import load_dotenv
from playwright.async_api import async_playwright
import google.genai as genai

# 1. Load API Key
_backend_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_backend_dir)
load_dotenv(os.path.join(_project_root, ".env"))
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    raise ValueError("Please set GEMINI_API_KEY (or GOOGLE_API_KEY) in your .env file")

# 2. Configuration
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 800
# Use the Flash model for faster speed, or the Computer Use model if you have access
MODEL_ID = "gemini-2.0-flash-exp" 

class WebAgent:
    def __init__(self):
        self.client = genai.Client(api_key=API_KEY)
        self.browser = None
        self.context = None
        self.page = None

    async def run_task(self, prompt, update_callback=None):
        print(f"[WebAgent] Starting task: {prompt}")
        summary = ""

        async with async_playwright() as p:
            prompt_l = prompt.lower()
            use_chrome = "chrome" in prompt_l
            # Safari automation is not directly supported by Playwright; use Chrome if requested,
            # otherwise Chromium. If Chrome channel is unavailable, fallback to Chromium.
            try:
                self.browser = await p.chromium.launch(
                    headless=False,
                    channel="chrome" if use_chrome else None,
                )
            except Exception:
                self.browser = await p.chromium.launch(headless=False)

            self.context = await self.browser.new_context(
                viewport={"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT}
            )
            self.page = await self.context.new_page()
            
            # Basic Logic: Go to Google and Search
            # (We use a simple script here for speed/reliability vs the complex Computer Use model which can be slow)
            try:
                if "youtube" in prompt.lower():
                    await self.page.goto("https://www.youtube.com")
                    if "search" in prompt.lower():
                        term = prompt.replace("search", "").replace("youtube", "").replace("for", "").strip()
                        await self.page.fill("input[name='search_query']", term)
                        await self.page.press("input[name='search_query']", "Enter")
                
                elif "amazon" in prompt.lower():
                    await self.page.goto("https://www.amazon.com")
                    if "search" in prompt.lower():
                        term = prompt.replace("search", "").replace("amazon", "").replace("for", "").strip()
                        await self.page.fill("#twotabsearchtextbox", term)
                        await self.page.press("#twotabsearchtextbox", "Enter")
                        
                else:
                    # Default to Google
                    await self.page.goto("https://www.google.com")
                    await self.page.fill("textarea[name='q']", prompt)
                    await self.page.press("textarea[name='q']", "Enter")

                # Wait for results to load
                await asyncio.sleep(2.5)
                
                # Take a screenshot to show the user what happened
                screenshot_bytes = await self.page.screenshot(type="jpeg")
                page_title = await self.page.title()
                if update_callback:
                    b64_img = base64.b64encode(screenshot_bytes).decode('utf-8')
                    await update_callback(b64_img, f"Navigated to: {page_title}")

                # Read page text and ask Gemini to produce a concise factual summary.
                page_text = await self.page.evaluate("() => document.body?.innerText || ''")
                page_text = " ".join(page_text.split())
                if len(page_text) > 12000:
                    page_text = page_text[:12000]

                browser_note = (
                    "Chrome mode requested." if use_chrome
                    else "Chromium mode used. (Safari direct automation is not supported by Playwright.)"
                )

                gemini_prompt = (
                    "You are extracting factual web results.\n"
                    f"User request: {prompt}\n"
                    f"Page title: {page_title}\n"
                    f"{browser_note}\n\n"
                    "Based only on this page text, provide:\n"
                    "1) Direct answer in 2-4 bullets.\n"
                    "2) If asking for scores/news, include the teams or headline names and dates visible.\n"
                    "3) If the page lacks enough info, say what is missing.\n\n"
                    f"Page text:\n{page_text}"
                )
                response = self.client.models.generate_content(
                    model=MODEL_ID,
                    contents=gemini_prompt,
                )
                summary = getattr(response, "text", "") or "No Gemini summary was produced."

                # Keep browser open for a few seconds so you can see it
                await asyncio.sleep(3)

            except Exception as e:
                print(f"[WebAgent] Error: {e}")
                summary = f"Web task failed: {e}"
            
            await self.browser.close()
            return summary

if __name__ == "__main__":
    agent = WebAgent()
    asyncio.run(agent.run_task("search google for NVIDIA stock price"))

    