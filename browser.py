"""简化的浏览器控制类，基于 Playwright"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, Any
from playwright.async_api import async_playwright, Browser as PlaywrightBrowser, Page, BrowserContext

logger = logging.getLogger(__name__)

# 持久化用户数据目录
USER_DATA_DIR = Path(__file__).parent / ".browser_data"

# CDP 连接地址（用于连接到已运行的 Chrome）
DEFAULT_CDP_URL = "http://localhost:9222"


class Browser:
    """简化的浏览器控制类"""
    
    def __init__(
        self,
        headless: bool = False,
        browser_type: str = "chromium",
        viewport_size: Optional[dict] = None,
        use_persistent: bool = True,
        connect_to_existing: bool = False,
        cdp_url: str = DEFAULT_CDP_URL,
    ):
        """
        初始化浏览器
        
        Args:
            headless: 是否无头模式
            browser_type: 浏览器类型 (chromium, firefox, webkit)
            viewport_size: 视口大小 {'width': 1920, 'height': 1080}
            use_persistent: 是否使用持久化上下文（保存cookies等）
            connect_to_existing: 是否连接到已运行的 Chrome 浏览器
            cdp_url: Chrome DevTools Protocol URL，默认 http://localhost:9222
        """
        self.headless = headless
        self.browser_type = browser_type
        self.viewport_size = viewport_size or {"width": 1280, "height": 720}
        self.use_persistent = use_persistent
        self.connect_to_existing = connect_to_existing
        self.cdp_url = cdp_url
        self._playwright = None
        self._browser: Optional[PlaywrightBrowser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._is_connected = False  # 是否是连接模式
        
    async def start(self):
        """启动浏览器"""
        if self._context is not None and self._page is not None:
            return  # 已经启动
            
        self._playwright = await async_playwright().start()
        
        # 模式1: 连接到已运行的 Chrome 浏览器
        if self.connect_to_existing:
            await self._connect_to_existing_browser()
            return
        
        # 模式2: 启动新的浏览器
        await self._launch_new_browser()
    
    async def _connect_to_existing_browser(self):
        """连接到已运行的 Chrome 浏览器"""
        try:
            logger.info(f"尝试连接到已运行的 Chrome: {self.cdp_url}")
            
            self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url)
            self._is_connected = True
            
            # 获取已有的上下文，或创建新的
            contexts = self._browser.contexts
            if contexts:
                self._context = contexts[0]
                logger.info(f"使用已有的浏览器上下文，共 {len(self._context.pages)} 个页面")
            else:
                self._context = await self._browser.new_context()
                logger.info("创建新的浏览器上下文")
            
            # 获取已有的页面，或创建新的
            if self._context.pages:
                self._page = self._context.pages[0]
                logger.info(f"使用已有的页面: {self._page.url}")
            else:
                self._page = await self._context.new_page()
                logger.info("创建新的页面")
            
            logger.info("✅ 成功连接到已运行的 Chrome 浏览器！")
            
        except Exception as e:
            logger.error(f"❌ 无法连接到 Chrome: {e}")
            logger.info("请确保已用以下命令启动 Chrome:")
            logger.info('  chrome.exe --remote-debugging-port=9222')
            raise RuntimeError(
                f"无法连接到 Chrome ({self.cdp_url})。\n"
                "请先用以下命令启动 Chrome:\n"
                '  Windows: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222\n'
                "  或关闭所有 Chrome 窗口后再运行上述命令"
            ) from e
    
    async def _launch_new_browser(self):
        """启动新的浏览器"""
        # 反检测启动参数
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--ignore-certificate-errors",
        ]
        
        # 确保用户数据目录存在
        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        if self.browser_type == "chromium" and self.use_persistent:
            # 使用持久化上下文 - 保存 cookies 和浏览器状态
            logger.info(f"使用持久化浏览器配置: {USER_DATA_DIR}")
            
            try:
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(USER_DATA_DIR),
                    headless=self.headless,
                    channel="chrome",  # 使用真实 Chrome
                    args=launch_args,
                    viewport=self.viewport_size,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    locale="en-US",
                    timezone_id="America/New_York",
                    permissions=["geolocation"],
                    java_script_enabled=True,
                    bypass_csp=True,
                    ignore_https_errors=True,
                )
            except Exception as e:
                logger.warning(f"Chrome 启动失败，尝试 Chromium: {e}")
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(USER_DATA_DIR),
                    headless=self.headless,
                    args=launch_args,
                    viewport=self.viewport_size,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    locale="en-US",
                    timezone_id="America/New_York",
                    java_script_enabled=True,
                    bypass_csp=True,
                    ignore_https_errors=True,
                )
            
            # 持久化上下文自动创建页面，获取或创建新页面
            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = await self._context.new_page()
        else:
            # 非持久化模式
            if self.browser_type == "chromium":
                try:
                    self._browser = await self._playwright.chromium.launch(
                        headless=self.headless,
                        channel="chrome",
                        args=launch_args
                    )
                except Exception:
                    self._browser = await self._playwright.chromium.launch(
                        headless=self.headless,
                        args=launch_args
                    )
            elif self.browser_type == "firefox":
                self._browser = await self._playwright.firefox.launch(headless=self.headless)
            elif self.browser_type == "webkit":
                self._browser = await self._playwright.webkit.launch(headless=self.headless)
            else:
                raise ValueError(f"不支持的浏览器类型: {self.browser_type}")
            
            self._context = await self._browser.new_context(
                viewport=self.viewport_size,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US",
                timezone_id="America/New_York",
                java_script_enabled=True,
            )
            self._page = await self._context.new_page()
        
        # 注入反检测脚本（仅在非连接模式下）
        if not self._is_connected:
            await self._page.add_init_script("""
                // 隐藏 webdriver 属性
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // 模拟真实的 plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // 模拟真实的 languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                
                // 隐藏自动化相关的属性
                window.chrome = { runtime: {} };
                
                // 覆盖 permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)
        
        logger.info(f"浏览器已启动 (headless={self.headless}, persistent={self.use_persistent})")
    
    async def close(self):
        """关闭浏览器"""
        try:
            if self._is_connected:
                # 连接模式下，不关闭浏览器，只断开连接
                logger.info("断开与 Chrome 的连接（浏览器保持运行）")
            else:
                # 非连接模式，正常关闭
                if not self.use_persistent and self._page:
                    await self._page.close()
                if self._context:
                    await self._context.close()
                if self._browser:
                    await self._browser.close()
            
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"关闭浏览器时出错: {e}")
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            self._is_connected = False
        logger.info("浏览器已关闭")
    
    @property
    def page(self) -> Page:
        """获取当前页面"""
        if self._page is None:
            raise RuntimeError("浏览器未启动，请先调用 start()")
        return self._page
    
    async def navigate(self, url: str, timeout: int = 60000):
        """导航到指定 URL
        
        Args:
            url: 目标 URL
            timeout: 超时时间（毫秒），默认60秒
        """
        await self.start()
        try:
            # 先尝试 networkidle，如果超时则使用 domcontentloaded
            await self.page.goto(url, wait_until="networkidle", timeout=timeout)
        except Exception as e:
            if "timeout" in str(e).lower():
                logger.warning(f"networkidle 超时，尝试 domcontentloaded: {url}")
                try:
                    await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                except Exception as e2:
                    logger.error(f"导航失败: {e2}")
                    raise
            else:
                raise
        logger.info(f"已导航到: {url}")
    
    async def get_url(self) -> str:
        """获取当前 URL"""
        await self.start()
        return self.page.url
    
    async def get_title(self) -> str:
        """获取页面标题"""
        await self.start()
        return await self.page.title()
    
    async def get_html(self) -> str:
        """获取页面 HTML"""
        await self.start()
        return await self.page.content()
    
    async def screenshot(self, path: Optional[str] = None) -> bytes:
        """截图"""
        await self.start()
        if path:
            await self.page.screenshot(path=path)
            return b""
        return await self.page.screenshot()
    
    async def click(self, selector: str):
        """点击元素"""
        await self.start()
        await self.page.click(selector)
        await asyncio.sleep(0.5)  # 等待页面响应
        logger.info(f"已点击: {selector}")
    
    async def fill(self, selector: str, text: str):
        """填充输入框"""
        await self.start()
        await self.page.fill(selector, text)
        logger.info(f"已填充 {selector}: {text[:50]}...")
    
    async def evaluate(self, script: str) -> Any:
        """执行 JavaScript"""
        await self.start()
        return await self.page.evaluate(script)
    
    async def wait_for_selector(self, selector: str, timeout: int = 30000):
        """等待元素出现"""
        await self.start()
        await self.page.wait_for_selector(selector, timeout=timeout)
    
    async def get_elements_info(self) -> list[dict]:
        """获取页面可交互元素信息"""
        await self.start()
        script = """
        () => {
            const elements = [];
            const selectors = ['a', 'button', 'input', 'textarea', 'select', '[onclick]', '[role="button"]'];
            
            selectors.forEach(selector => {
                document.querySelectorAll(selector).forEach((el, index) => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        const text = el.textContent?.trim() || el.value || el.placeholder || '';
                        const id = el.id || '';
                        const className = el.className || '';
                        
                        elements.push({
                            index: elements.length,
                            tag: el.tagName.toLowerCase(),
                            text: text.substring(0, 100),
                            id: id,
                            className: className.substring(0, 50),
                            selector: selector,
                            xpath: getXPath(el),
                            visible: true
                        });
                    }
                });
            });
            
            function getXPath(element) {
                if (element.id !== '') {
                    return '//*[@id="' + element.id + '"]';
                }
                if (element === document.body) {
                    return '/html/body';
                }
                let ix = 0;
                const siblings = element.parentNode.childNodes;
                for (let i = 0; i < siblings.length; i++) {
                    const sibling = siblings[i];
                    if (sibling === element) {
                        return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                    }
                    if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                        ix++;
                    }
                }
            }
            
            return elements;
        }
        """
        return await self.page.evaluate(script)
    
    async def scroll(self, direction: str = "down", amount: int = 500):
        """滚动页面
        
        Args:
            direction: 滚动方向 ("up", "down", "left", "right")
            amount: 滚动距离（像素）
        """
        await self.start()
        if direction == "down":
            await self.page.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == "up":
            await self.page.evaluate(f"window.scrollBy(0, -{amount})")
        elif direction == "right":
            await self.page.evaluate(f"window.scrollBy({amount}, 0)")
        elif direction == "left":
            await self.page.evaluate(f"window.scrollBy(-{amount}, 0)")
        await asyncio.sleep(0.3)
        logger.info(f"已滚动: {direction} {amount}px")
    
    async def go_back(self):
        """返回上一页"""
        await self.start()
        try:
            await self.page.go_back(wait_until="domcontentloaded", timeout=30000)
        except Exception:
            await self.page.go_back(wait_until="load", timeout=30000)
        logger.info("已返回上一页")
    
    async def reload(self):
        """刷新当前页面"""
        await self.start()
        await self.page.reload(wait_until="domcontentloaded", timeout=60000)
        logger.info("已刷新页面")
    
    async def go_forward(self):
        """前进到下一页"""
        await self.start()
        await self.page.go_forward(wait_until="networkidle")
        logger.info("已前进到下一页")
    
    async def press_key(self, key: str):
        """按键
        
        Args:
            key: 按键名称，如 "Enter", "Tab", "Escape", "ArrowDown" 等
        """
        await self.start()
        await self.page.keyboard.press(key)
        await asyncio.sleep(0.3)
        logger.info(f"已按键: {key}")
    
    async def get_text(self) -> str:
        """获取页面纯文本内容"""
        await self.start()
        text = await self.page.evaluate("() => document.body.innerText")
        return text
    
    async def get_page_info(self) -> dict:
        """获取页面综合信息"""
        await self.start()
        return {
            "url": self.page.url,
            "title": await self.page.title(),
            "text_length": len(await self.get_text())
        }
    
    async def wait_for_load(self, timeout: int = 30000):
        """等待页面加载完成"""
        await self.start()
        await self.page.wait_for_load_state("networkidle", timeout=timeout)
        logger.info("页面加载完成")
    
    async def hover(self, selector: str):
        """悬停在元素上"""
        await self.start()
        await self.page.hover(selector)
        await asyncio.sleep(0.3)
        logger.info(f"已悬停: {selector}")
    
    async def select_option(self, selector: str, value: str):
        """选择下拉框选项"""
        await self.start()
        await self.page.select_option(selector, value)
        logger.info(f"已选择: {selector} -> {value}")

    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
