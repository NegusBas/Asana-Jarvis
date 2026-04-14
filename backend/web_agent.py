import os
import time
import asyncio
import base64
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from google import genai
from google.genai import types

# 1. Load API Key
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("Please set GEMINI_API_KEY in your .env file")

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
        
        async with async_playwright() as p:
            # HEADLESS=FALSE MEANS YOU SEE THE BROWSER!
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
                await asyncio.sleep(2)
                
                # Take a screenshot to show the user what happened
                screenshot_bytes = await self.page.screenshot(type="jpeg")
                if update_callback:
                    b64_img = base64.b64encode(screenshot_bytes).decode('utf-8')
                    title = await self.page.title()
                    await update_callback(b64_img, f"Navigated to: {title}")

                # Keep browser open for a few seconds so you can see it
                await asyncio.sleep(5)

            except Exception as e:
                print(f"[WebAgent] Error: {e}")
            
            await self.browser.close()
            return "Task completed."

if __name__ == "__main__":
    agent = WebAgent()
    asyncio.run(agent.run_task("search google for NVIDIA stock price"))

    