import os
import sys
import time
import uuid
import json
import random
import logging
import asyncio
import argparse
from quart import Quart, request, jsonify
from camoufox.async_api import AsyncCamoufox
from patchright.async_api import async_playwright


COLORS = {
    'MAGENTA': '\033[35m',
    'BLUE': '\033[34m',
    'GREEN': '\033[32m',
    'YELLOW': '\033[33m',
    'RED': '\033[31m',
    'RESET': '\033[0m',
}


class CustomLogger(logging.Logger):
    @staticmethod
    def format_message(level, color, message):
        timestamp = time.strftime('%H:%M:%S')
        return f"[{timestamp}] [{COLORS.get(color)}{level}{COLORS.get('RESET')}] -> {message}"

    def debug(self, message, *args, **kwargs):
        super().debug(self.format_message('DEBUG', 'MAGENTA', message), *args, **kwargs)

    def info(self, message, *args, **kwargs):
        super().info(self.format_message('INFO', 'BLUE', message), *args, **kwargs)

    def success(self, message, *args, **kwargs):
        super().info(self.format_message('SUCCESS', 'GREEN', message), *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        super().warning(self.format_message('WARNING', 'YELLOW', message), *args, **kwargs)

    def error(self, message, *args, **kwargs):
        super().error(self.format_message('ERROR', 'RED', message), *args, **kwargs)


logging.setLoggerClass(CustomLogger)
logger = logging.getLogger("TurnstileAPIServer")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)


class TurnstileAPIServer:
    HTML_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Turnstile Solver</title>
        <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async></script>
        <script>
            async function fetchIP() {
                try {
                    const response = await fetch('https://api64.ipify.org?format=json');
                    const data = await response.json();
                    document.getElementById('ip-display').innerText = `Your IP: ${data.ip}`;
                } catch (error) {
                    console.error('Error fetching IP:', error);
                    document.getElementById('ip-display').innerText = 'Failed to fetch IP';
                }
            }
            window.onload = fetchIP;
        </script>
    </head>
    <body>
        <!-- cf turnstile -->
        <p id="ip-display">Fetching your IP...</p>
    </body>
    </html>
    """
    
    # 【修改点 1】: 在 __init__ 方法中增加一个 no_sandbox 参数
    def __init__(self, headless: bool, useragent: str, debug: bool, browser_type: str, thread: int, proxy_support: bool, no_sandbox: bool):
        self.app = Quart(__name__)
        self.debug = debug
        self.results = self._load_results()
        self.browser_type = browser_type
        self.headless = headless
        self.useragent = useragent
        self.thread_count = thread
        self.proxy_support = proxy_support
        self.browser_pool = asyncio.Queue()
        self.browser_args = []
        if useragent:
            self.browser_args.append(f"--user-agent={useragent}")
        # 如果 no_sandbox 为 True, 就把 '--no-sandbox' 添加到启动参数列表里
        if no_sandbox:
            self.browser_args.append('--no-sandbox')

        self._setup_routes()

    @staticmethod
    def _load_results():
        """Load previous results from results.json."""
        try:
            if os.path.exists("results.json"):
                with open("results.json", "r") as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Error loading results: {str(e)}. Starting with an empty results dictionary.")
        return {}

    def _save_results(self):
        """Save results to results.json."""
        try:
            with open("results.json", "w") as result_file:
                json.dump(self.results, result_file, indent=4)
        except IOError as e:
            logger.error(f"Error saving results to file: {str(e)}")

    def _setup_routes(self) -> None:
        """Set up the application routes."""
        self.app.before_serving(self._startup)
        self.app.route('/turnstile', methods=['GET'])(self.process_turnstile)
        self.app.route('/result', methods=['GET'])(self.get_result)
        self.app.route('/')(self.index)

    async def _startup(self) -> None:
        """Initialize the browser and page pool on startup."""
        logger.info("Starting browser initialization")
        try:
            await self._initialize_browser()
        except Exception as e:
            logger.error(f"Failed to initialize browser: {str(e)}")
            raise

    async def _initialize_browser(self) -> None:
        """Initialize the browser and create the page pool."""
        
        # 【修改点 2】: 在启动 Camoufox 时，把 self.browser_args 传递进去
        if self.browser_type in ['chromium', 'chrome', 'msedge']:
            playwright = await async_playwright().start()
        elif self.browser_type == "camoufox":
            # Camoufox 的初始化现在也接收 args
            camoufox = AsyncCamoufox(headless=self.headless, args=self.browser_args)

        for _ in range(self.thread_count):
            if self.browser_type in ['chromium', 'chrome', 'msedge']:
                browser = await playwright.chromium.launch(
                    channel=self.browser_type,
                    headless=self.headless,
                    args=self.browser_args
                )

            elif self.browser_type == "camoufox":
                # Camoufox 的 .start() 不需要额外参数，因为已经在初始化时传递了
                browser = await camoufox.start()

            await self.browser_pool.put((_+1, browser))

            if self.debug:
                logger.success(f"Browser {_ + 1} initialized successfully")

        logger.success(f"Browser pool initialized with {self.browser_pool.qsize()} browsers")


    async def _solve_turnstile(self, task_id: str, url: str, sitekey: str, action: str = None, cdata: str = None):
        """Solve the Turnstile challenge."""
        proxy = None

        index, browser = await self.browser_pool.get()

        if self.proxy_support:
            proxy_file_path = os.path.join(os.getcwd(), "proxies.txt")

            with open(proxy_file_path) as proxy_file:
                proxies = [line.strip() for line in proxy_file if line.strip()]

            proxy = random.choice(proxies) if proxies else None

            if proxy:
                parts = proxy.split(':')
                # 修正了代理格式解析逻辑，以支持 user:pass@host:port
                if '@' in proxy: # 包含认证信息
                    auth, loc = proxy.split('@')
                    user, password = auth.split(':')
                    host, port = loc.split(':')
                    # 假设协议是 http，可以根据需要修改
                    server_url = f"http://{host}:{port}"
                    context = await browser.new_context(proxy={"server": server_url, "username": user, "password": password})
                elif len(parts) == 2: # 只有 host:port
                    host, port = parts
                    server_url = f"http://{host}:{port}"
                    context = await browser.new_context(proxy={"server": server_url})
                else:
                    raise ValueError("Invalid proxy format in proxies.txt. Use host:port or user:pass@host:port.")
            else:
                context = await browser.new_context()
        else:
            context = await browser.new_context()

        page = await context.new_page()

        start_time = time.time()

        try:
            if self.debug:
                logger.debug(f"Browser {index}: Starting Turnstile solve for URL: {url} with Sitekey: {sitekey} | Proxy: {proxy}")
                logger.debug(f"Browser {index}: Setting up page data and route")

            url_with_slash = url + "/" if not url.endswith("/") else url
            turnstile_div = f'<div class="cf-turnstile" style="background: white;" data-sitekey="{sitekey}"' + (f' data-action="{action}"' if action else '') + (f' data-cdata="{cdata}"' if cdata else '') + '></div>'
            page_data = self.HTML_TEMPLATE.replace("<!-- cf turnstile -->", turnstile_div)

            await page.route(url_with_slash, lambda route: route.fulfill(body=page_data, status=200))
            await page.goto(url_with_slash)

            if self.debug:
                logger.debug(f"Browser {index}: Setting up Turnstile widget dimensions")

            await page.eval_on_selector("//div[@class='cf-turnstile']", "el => el.style.width = '70px'")

            if self.debug:
                logger.debug(f"Browser {index}: Starting Turnstile response retrieval loop")

            for _ in range(10):
                try:
                    turnstile_check = await page.input_value("[name=cf-turnstile-response]", timeout=2000)
                    if turnstile_check == "":
                        if self.debug:
                            logger.debug(f"Browser {index}: Attempt {_} - No Turnstile response yet")
                        
                        await page.locator("//div[@class='cf-turnstile']").click(timeout=1000)
                        await asyncio.sleep(0.5)
                    else:
                        elapsed_time = round(time.time() - start_time, 3)

                        logger.success(f"Browser {index}: Successfully solved captcha - {COLORS.get('MAGENTA')}{turnstile_check[:10]}{COLORS.get('RESET')} in {COLORS.get('GREEN')}{elapsed_time}{COLORS.get('RESET')} Seconds")

                        self.results[task_id] = {"value": turnstile_check, "elapsed_time": elapsed_time}
                        self._save_results()
                        break
                except:
                    pass

            if self.results.get(task_id) == "CAPTCHA_NOT_READY":
                elapsed_time = round(time.time() - start_time, 3)
                self.results[task_id] = {"value": "CAPTCHA_FAIL", "elapsed_time": elapsed_time}
                if self.debug:
                    logger.error(f"Browser {index}: Error solving Turnstile in {COLORS.get('RED')}{elapsed_time}{COLORS.get('RESET')} Seconds")
        except Exception as e:
            elapsed_time = round(time.time() - start_time, 3)
            self.results[task_id] = {"value": "CAPTCHA_FAIL", "elapsed_time": elapsed_time}
            if self.debug:
                logger.error(f"Browser {index}: Error solving Turnstile: {str(e)}")
        finally:
            if self.debug:
                logger.debug(f"Browser {index}: Clearing page state")

            await context.close()
            await self.browser_pool.put((index, browser))

    async def process_turnstile(self):
        """Handle the /turnstile endpoint requests."""
        url = request.args.get('url')
        sitekey = request.args.get('sitekey')
        action = request.args.get('action')
        cdata = request.args.get('cdata')

        if not url or not sitekey:
            return jsonify({
                "status": "error",
                "error": "Both 'url' and 'sitekey' are required"
            }), 400

        task_id = str(uuid.uuid4())
        self.results[task_id] = "CAPTCHA_NOT_READY"

        try:
            asyncio.create_task(self._solve_turnstile(task_id=task_id, url=url, sitekey=sitekey, action=action, cdata=cdata))

            if self.debug:
                logger.debug(f"Request completed with taskid {task_id}.")
            return jsonify({"task_id": task_id}), 202
        except Exception as e:
            logger.error(f"Unexpected error processing request: {str(e)}")
            return jsonify({
                "status": "error",
                "error": str(e)
            }), 500

    async def get_result(self):
        """Return solved data"""
        task_id = request.args.get('id')

        if not task_id or task_id not in self.results:
            return jsonify({"status": "error", "error": "Invalid task ID/Request parameter"}), 400

        result = self.results[task_id]
        status_code = 200

        if "CAPTCHA_FAIL" in result:
            status_code = 422

        return result, status_code

    @staticmethod
    async def index():
        """Serve the API documentation page."""
        return """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Turnstile Solver API</title>
                <script src="https://cdn.tailwindcss.com"></script>
            </head>
            <body class="bg-gray-900 text-gray-200 min-h-screen flex items-center justify-center">
                <div class="bg-gray-800 p-8 rounded-lg shadow-md max-w-2xl w-full border border-red-500">
                    <h1 class="text-3xl font-bold mb-6 text-center text-red-500">Welcome to Turnstile Solver API</h1>

                    <p class="mb-4 text-gray-300">To use the turnstile service, send a GET request to 
                       <code class="bg-red-700 text-white px-2 py-1 rounded">/turnstile</code> with the following query parameters:</p>

                    <ul class="list-disc pl-6 mb-6 text-gray-300">
                        <li><strong>url</strong>: The URL where Turnstile is to be validated</li>
                        <li><strong>sitekey</strong>: The site key for Turnstile</li>
                    </ul>

                    <div class="bg-gray-700 p-4 rounded-lg mb-6 border border-red-500">
                        <p class="font-semibold mb-2 text-red-400">Example usage:</p>
                        <code class="text-sm break-all text-red-300">/turnstile?url=https://example.com&sitekey=sitekey</code>
                    </div>

                    <div class="bg-red-900 border-l-4 border-red-600 p-4 mb-6">
                        <p class="text-red-200 font-semibold">This project is inspired by 
                           <a href="https://github.com/Body-Alhoha/turnaround" class="text-red-300 hover:underline">Turnaround</a> 
                           and is currently maintained by 
                           <a href="https://github.com/Theyka" class="text-red-300 hover:underline">Theyka</a> 
                           and <a href="https://github.com/sexfrance" class="text-red-300 hover:underline">Sexfrance</a>.</p>
                    </div>
                </div>
            </body>
            </html>
        """

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Turnstile API Server")

    parser.add_argument('--no-sandbox', action='store_true', help='(For Colab/Docker) Add --no-sandbox flag to browser launch arguments.')
    parser.add_argument('--headless', action='store_true', help='Run the browser in headless mode.')
    parser.add_argument('--useragent', type=str, default=None, help='Specify a custom User-Agent string for the browser.')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode for additional logging.')
    parser.add_argument('--browser_type', type=str, default='camoufox', help='Specify the browser type. (Default: camoufox)')
    parser.add_argument('--thread', type=int, default=1, help='Set the number of browser threads to use.')
    parser.add_argument('--proxy', action='store_true', help='Enable proxy support from proxies.txt.')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='IP address for the API solver to run on.')
    parser.add_argument('--port', type=str, default='5000', help='Port for the API solver to listen on.')
    
    return parser.parse_args()
r.add_argument('--browser_type', type=str, default='camoufox', help='Specify the browser type. (Default: camoufox)')
    parser.add_argument('--thread', type=int, default=1, help='Set the number of browser threads to use.')
    
    # 【核心修复】将 --proxy 的类型从 bool 改为 action='store_true'
    # 这样只要命令中出现 --proxy，它的值就是 True，不再需要跟一个参数。
    parser.add_argument('--proxy', action='store_true', help='Enable proxy support from proxies.txt.')
    
    parser.add_argument('--host', type=str, default='127.0.0.1', help='IP address for the API solver to run on.')
    parser.add_argument('--port', type=str, default='5000', help='Port for the API solver to listen on.')
    
    return parser.parse_args()

# 【修改点 4】: 在 create_app 函数签名中增加 no_sandbox
def create_app(headless: bool, useragent: str, debug: bool, browser_type: str, thread: int, proxy_support: bool, no_sandbox: bool) -> Quart:
    # 把 no_sandbox 传递给 TurnstileAPIServer 的构造函数
    server = TurnstileAPIServer(headless=headless, useragent=useragent, debug=debug, browser_type=browser_type, thread=thread, proxy_support=proxy_support, no_sandbox=no_sandbox)
    return server.app


if __name__ == '__main__':
    args = parse_args()
    browser_types = [
        'chromium',
        'chrome',
        'msedge',
        'camoufox',
    ]
    if args.browser_type not in browser_types:
        logger.error(f"Unknown browser type: {COLORS.get('RED')}{args.browser_type}{COLORS.get('RESET')} Available browser types: {browser_types}")
    elif args.headless is True and args.useragent is None and "camoufox" not in args.browser_type:
        logger.error(f"You must specify a {COLORS.get('YELLOW')}User-Agent{COLORS.get('RESET')} for Turnstile Solver or use {COLORS.get('GREEN')}camoufox{COLORS.get('RESET')} without useragent")
    else:
        # 【修改点 5】: 把解析到的 no_sandbox 参数传递给 create_app
        app = create_app(headless=args.headless, debug=args.debug, useragent=args.useragent, browser_type=args.browser_type, thread=args.thread, proxy_support=args.proxy, no_sandbox=args.no_sandbox)
        app.run(host=args.host, port=int(args.port))
