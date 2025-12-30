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
    
    async def click(self, selector: str, timeout: int = 8000):
        """
        点击元素 - 支持多种选择器格式和智能匹配
        
        Args:
            selector: CSS 选择器、XPath、文本匹配或 data-agent-idx
            timeout: 超时时间（毫秒）
        """
        await self.start()
        
        # 清理选择器
        selector = selector.strip()
        
        # 尝试多种选择器策略
        strategies = []
        
        # 1. 如果是 data-agent-idx 格式
        if selector.startswith("[data-agent-idx"):
            strategies.append(selector)
        
        # 2. 原始选择器
        strategies.append(selector)
        
        # 3. 如果看起来像文本（不是选择器语法），尝试文本匹配
        selector_lower = selector.lower()
        is_text_like = not selector.startswith(("#", ".", "[", "/", "xpath=")) and len(selector) > 2
        
        if is_text_like:
            # 尝试按文本匹配按钮和链接
            strategies.extend([
                f'button:has-text("{selector}")',
                f'a:has-text("{selector}")',
                f'text="{selector}"',
                f'[role="button"]:has-text("{selector}")',
            ])
        
        # 4. PCPartPicker 特殊处理
        current_url = self.page.url.lower() if self.page else ""
        is_pcpartpicker = "pcpartpicker" in current_url
        
        if is_pcpartpicker:
            # PCPartPicker 配件选择按钮的常见模式
            part_keywords = {
                "cpu": ["Choose A CPU", "cpu", "processor"],
                "cooler": ["Choose A CPU Cooler", "cooler", "cooling"],
                "motherboard": ["Choose A Motherboard", "motherboard", "mobo"],
                "memory": ["Choose Memory", "memory", "ram"],
                "storage": ["Choose Storage", "storage", "ssd", "hdd"],
                "video": ["Choose A Video Card", "video card", "gpu", "graphics"],
                "case": ["Choose A Case", "case", "chassis"],
                "power": ["Choose A Power Supply", "power supply", "psu"],
            }
            
            for key, keywords in part_keywords.items():
                if any(kw in selector_lower for kw in keywords):
                    for kw in keywords:
                        strategies.extend([
                            f'a:has-text("{kw}")',
                            f'button:has-text("{kw}")',
                            f'td a:has-text("{kw}")',
                            f'.td__component a:has-text("Choose")',
                        ])
                    break
            
            # PCPartPicker 的 Add 按钮
            if "add" in selector_lower:
                strategies.extend([
                    'button:has-text("Add")',
                    '.button--add',
                    '[class*="add"]',
                    'button.btn-primary',
                ])
        
        # 5. 如果是简单的 ID 选择器但没找到，尝试包含匹配
        if selector.startswith("#"):
            id_name = selector[1:]
            if "_" in id_name:
                keyword = id_name.split("_")[-1]
            else:
                keyword = id_name
            strategies.extend([
                f'[id*="{keyword}" i]',
                f'[class*="{keyword}" i]',
                f'button:has-text("{keyword}")',
                f'a:has-text("{keyword}")',
            ])
        
        # 6. XPath 选择器
        if selector.startswith("//") or selector.startswith("xpath="):
            xpath = selector.replace("xpath=", "")
            strategies.insert(0, f'xpath={xpath}')
        
        # 7. 通用文本搜索（最后的尝试）
        if is_text_like:
            # 提取可能的关键词
            words = selector.replace("_", " ").replace("-", " ").split()
            for word in words:
                if len(word) > 2:
                    strategies.append(f'*:has-text("{word}")')
        
        # 去重
        seen = set()
        unique_strategies = []
        for s in strategies:
            if s not in seen:
                seen.add(s)
                unique_strategies.append(s)
        
        last_error = None
        for strategy in unique_strategies:
            try:
                # 先检查元素是否存在
                element = await self.page.wait_for_selector(strategy, timeout=timeout, state="visible")
                if element:
                    # 滚动到元素位置
                    await element.scroll_into_view_if_needed()
                    await asyncio.sleep(0.2)
                    await element.click()
                    await asyncio.sleep(0.5)
                    logger.info(f"✅ 点击成功: {strategy}")
                    return
            except Exception as e:
                last_error = e
                logger.debug(f"选择器 '{strategy}' 失败: {e}")
                continue
        
        # 所有策略都失败，尝试使用 JavaScript 点击
        try:
            clicked = await self._js_click_fallback(selector)
            if clicked:
                return
        except Exception as e:
            logger.debug(f"JS 点击也失败: {e}")
        
        # 抛出错误
        raise Exception(f"点击失败: 尝试了 {len(unique_strategies)} 种选择器都未找到元素。原始: {selector}")
    
    async def _js_click_fallback(self, selector: str) -> bool:
        """使用 JavaScript 作为点击的后备方案"""
        selector_lower = selector.lower()
        
        # 尝试通过文本内容查找并点击
        script = """
        (searchText) => {
            const searchLower = searchText.toLowerCase();
            
            // 查找包含文本的可点击元素
            const clickables = document.querySelectorAll('a, button, [role="button"], [onclick]');
            
            for (const el of clickables) {
                const text = (el.textContent || '').toLowerCase();
                const id = (el.id || '').toLowerCase();
                const className = (el.className || '').toLowerCase();
                
                if (text.includes(searchLower) || id.includes(searchLower) || className.includes(searchLower)) {
                    el.scrollIntoView({ behavior: 'instant', block: 'center' });
                    el.click();
                    return true;
                }
            }
            return false;
        }
        """
        
        # 提取搜索关键词
        search_text = selector.lstrip("#.").replace("_", " ").replace("-", " ")
        
        try:
            result = await self.page.evaluate(script, search_text)
            if result:
                await asyncio.sleep(0.5)
                logger.info(f"✅ JS 点击成功: {search_text}")
                return True
        except Exception as e:
            logger.debug(f"JS 点击失败: {e}")
        
        return False
    
    async def fill(self, selector: str, text: str, timeout: int = 10000):
        """
        填充输入框 - 支持多种选择器格式
        
        Args:
            selector: CSS 选择器、XPath 或其他
            text: 要填充的文本
            timeout: 超时时间（毫秒）
        """
        await self.start()
        
        strategies = [selector]
        
        # 如果是简单选择器，添加备选策略
        if selector.startswith("#") or selector.startswith("."):
            keyword = selector.lstrip("#.")
            strategies.extend([
                f'input[name*="{keyword}"]',
                f'input[placeholder*="{keyword}"]',
                f'textarea[name*="{keyword}"]',
                f'[id*="{keyword}"]',
            ])
        
        # 如果看起来像文本描述
        if not selector.startswith(("#", ".", "[", "/")):
            strategies.extend([
                f'input[placeholder*="{selector}"]',
                f'input[name*="{selector}"]',
                f'textarea[placeholder*="{selector}"]',
            ])
        
        last_error = None
        for strategy in strategies:
            try:
                element = await self.page.wait_for_selector(strategy, timeout=timeout, state="visible")
                if element:
                    await element.fill(text)
                    logger.info(f"✅ 已填充 {strategy}: {text[:30]}...")
                    return
            except Exception as e:
                last_error = e
                continue
        
        raise Exception(f"填充失败: 未找到输入框。选择器: {selector}。错误: {last_error}")
    
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
    
    async def get_pruned_dom(self, max_elements: int = 50) -> dict:
        """
        获取剪枝后的 DOM 树 - 只保留可交互元素和关键信息
        
        Args:
            max_elements: 最大返回元素数量
            
        Returns:
            包含剪枝后 DOM 信息的字典
        """
        await self.start()
        
        # 高级 DOM 剪枝脚本
        script = """
        (maxElements) => {
            const result = {
                url: window.location.href,
                title: document.title,
                viewport: {
                    width: window.innerWidth,
                    height: window.innerHeight,
                    scrollY: window.scrollY
                },
                elements: []
            };
            
            // 可交互元素选择器（按重要性排序）
            const interactiveSelectors = [
                'button:not([disabled])',
                'a[href]',
                'input:not([type="hidden"]):not([disabled])',
                'textarea:not([disabled])',
                'select:not([disabled])',
                '[role="button"]',
                '[role="link"]',
                '[role="checkbox"]',
                '[role="radio"]',
                '[role="tab"]',
                '[role="menuitem"]',
                '[onclick]',
                '[data-action]',
                '[contenteditable="true"]'
            ];
            
            // 要排除的元素（广告、追踪、无关紧要的）
            const excludePatterns = [
                /^ad[-_]?/i, /advertisement/i, /tracking/i, /analytics/i,
                /cookie[-_]?banner/i, /popup/i, /modal[-_]?overlay/i,
                /social[-_]?share/i, /newsletter/i
            ];
            
            // 检查元素是否应该被排除
            function shouldExclude(el) {
                const id = el.id || '';
                const className = el.className || '';
                const combined = id + ' ' + className;
                return excludePatterns.some(pattern => pattern.test(combined));
            }
            
            // 检查元素是否在视口内或附近
            function isNearViewport(rect) {
                const buffer = 200; // 视口外200px也算
                return (
                    rect.bottom >= -buffer &&
                    rect.top <= window.innerHeight + buffer &&
                    rect.right >= -buffer &&
                    rect.left <= window.innerWidth + buffer
                );
            }
            
            // 获取元素的最佳选择器
            function getBestSelector(el, index) {
                const tag = el.tagName.toLowerCase();
                
                // 优先使用 ID
                if (el.id) {
                    return `#${el.id}`;
                }
                
                // 使用 data-testid 或 data-id
                if (el.dataset.testid) {
                    return `[data-testid="${el.dataset.testid}"]`;
                }
                if (el.dataset.id) {
                    return `[data-id="${el.dataset.id}"]`;
                }
                
                // 使用 name 属性
                if (el.name) {
                    return `[name="${el.name}"]`;
                }
                
                // 使用唯一的 class 组合
                if (el.className && typeof el.className === 'string') {
                    const classes = el.className.trim().split(/\\s+/).filter(c => c && !c.match(/^(js-|is-|has-)/)).slice(0, 2).join('.');
                    if (classes) {
                        const selector = tag + '.' + classes;
                        if (document.querySelectorAll(selector).length === 1) {
                            return selector;
                        }
                    }
                }
                
                // 🔑 使用文本内容（最稳定的选择器）
                const text = (el.textContent || '').trim().substring(0, 30);
                if (text && text.length > 2) {
                    // 清理文本，移除特殊字符
                    const cleanText = text.replace(/[\"'\\n\\r\\t]/g, '').trim();
                    if (cleanText.length > 2) {
                        return `${tag}:has-text("${cleanText}")`;
                    }
                }
                
                // 使用 href 属性（链接）
                if (el.href && tag === 'a') {
                    const href = el.getAttribute('href');
                    if (href && !href.startsWith('javascript:') && href.length < 50) {
                        return `a[href="${href}"]`;
                    }
                }
                
                // 使用 placeholder（输入框）
                if (el.placeholder) {
                    return `${tag}[placeholder="${el.placeholder}"]`;
                }
                
                // 最后使用标签+索引（尽量避免）
                return `${tag}:nth-of-type(${index + 1})`;
            }
            
            // 提取元素的简洁描述
            function getElementDescription(el) {
                // 获取可见文本
                let text = '';
                if (el.tagName === 'INPUT') {
                    text = el.value || el.placeholder || '';
                } else if (el.tagName === 'IMG') {
                    text = el.alt || '';
                } else {
                    // 只获取直接文本，不包括子元素
                    text = el.textContent?.trim() || '';
                }
                // 限制长度
                return text.substring(0, 60).replace(/\\s+/g, ' ');
            }
            
            // 收集所有可交互元素
            const allElements = [];
            const seen = new Set();
            
            interactiveSelectors.forEach(selector => {
                try {
                    document.querySelectorAll(selector).forEach(el => {
                        if (seen.has(el)) return;
                        seen.add(el);
                        
                        const rect = el.getBoundingClientRect();
                        
                        // 过滤条件
                        if (rect.width < 5 || rect.height < 5) return; // 太小
                        if (!isNearViewport(rect)) return; // 不在视口附近
                        if (shouldExclude(el)) return; // 被排除
                        if (window.getComputedStyle(el).display === 'none') return; // 隐藏
                        if (window.getComputedStyle(el).visibility === 'hidden') return;
                        
                        allElements.push({
                            el: el,
                            rect: rect,
                            inViewport: rect.top >= 0 && rect.top < window.innerHeight
                        });
                    });
                } catch (e) {}
            });
            
            // 按位置排序（从上到下，从左到右）
            allElements.sort((a, b) => {
                // 优先显示视口内的元素
                if (a.inViewport !== b.inViewport) {
                    return a.inViewport ? -1 : 1;
                }
                // 按 Y 坐标排序
                if (Math.abs(a.rect.top - b.rect.top) > 20) {
                    return a.rect.top - b.rect.top;
                }
                // Y 坐标相近时按 X 排序
                return a.rect.left - b.rect.left;
            });
            
            // 限制数量并格式化
            allElements.slice(0, maxElements).forEach((item, index) => {
                const el = item.el;
                const rect = item.rect;
                
                // 添加索引标记到元素（用于后续定位）
                el.setAttribute('data-agent-idx', index.toString());
                
                const tag = el.tagName.toLowerCase();
                const type = el.type || '';
                const text = getElementDescription(el);
                const selector = getBestSelector(el, index);
                
                // 构建简洁的元素信息
                const elementInfo = {
                    idx: index,
                    tag: tag,
                    selector: selector
                };
                
                // 只添加有意义的属性
                if (text) elementInfo.text = text;
                if (type && type !== 'submit') elementInfo.type = type;
                if (el.href) elementInfo.href = el.href.substring(0, 80);
                if (el.name) elementInfo.name = el.name;
                if (el.placeholder) elementInfo.placeholder = el.placeholder.substring(0, 30);
                if (el.checked !== undefined) elementInfo.checked = el.checked;
                if (el.disabled) elementInfo.disabled = true;
                
                // 添加位置信息（用于视觉对照）
                elementInfo.pos = {
                    x: Math.round(rect.left + rect.width / 2),
                    y: Math.round(rect.top + rect.height / 2)
                };
                
                result.elements.push(elementInfo);
            });
            
            return result;
        }
        """
        
        try:
            dom_info = await self.page.evaluate(script, max_elements)
            logger.info(f"DOM 剪枝完成: 提取了 {len(dom_info.get('elements', []))} 个可交互元素")
            return dom_info
        except Exception as e:
            logger.error(f"DOM 剪枝失败: {e}")
            return {
                "url": self.page.url,
                "title": await self.page.title(),
                "elements": [],
                "error": str(e)
            }
    
    async def get_compact_state(self, include_screenshot: bool = True, 
                                 screenshot_quality: int = 50,
                                 max_elements: int = 40) -> dict:
        """
        获取页面的紧凑状态（用于多模态 Agent）
        
        Args:
            include_screenshot: 是否包含截图
            screenshot_quality: 截图质量 (1-100)
            max_elements: 最大元素数量
            
        Returns:
            包含截图和剪枝 DOM 的字典
        """
        await self.start()
        
        state = {
            "url": self.page.url,
            "title": await self.page.title(),
        }
        
        # 获取剪枝后的 DOM
        dom_info = await self.get_pruned_dom(max_elements)
        state["elements"] = dom_info.get("elements", [])
        state["viewport"] = dom_info.get("viewport", {})
        
        # 获取截图
        if include_screenshot:
            try:
                # 使用 JPEG 格式和较低质量减少大小
                screenshot = await self.page.screenshot(
                    type="jpeg",
                    quality=screenshot_quality,
                    full_page=False  # 只截取视口
                )
                state["screenshot"] = screenshot
                state["screenshot_size"] = len(screenshot)
                logger.info(f"截图大小: {len(screenshot) / 1024:.1f} KB")
            except Exception as e:
                logger.warning(f"截图失败: {e}")
                state["screenshot"] = None
        
        return state
    
    def format_elements_for_llm(self, elements: list, max_chars: int = 3000) -> str:
        """
        将元素列表格式化为 LLM 友好的文本
        
        Args:
            elements: 元素列表
            max_chars: 最大字符数
            
        Returns:
            格式化的文本
        """
        if not elements:
            return "页面上没有找到可交互元素"
        
        lines = ["可交互元素列表 (使用 idx 或 selector 进行操作):"]
        lines.append("-" * 50)
        
        for el in elements:
            idx = el.get("idx", "?")
            tag = el.get("tag", "unknown")
            text = el.get("text", "")
            selector = el.get("selector", "")
            el_type = el.get("type", "")
            href = el.get("href", "")
            
            # 构建简洁的描述
            parts = [f"[{idx}]", f"<{tag}>"]
            
            if el_type:
                parts.append(f"type={el_type}")
            if text:
                parts.append(f'"{text}"')
            if href:
                # 简化 URL
                short_href = href.split("?")[0][-40:] if len(href) > 40 else href
                parts.append(f"→{short_href}")
            
            parts.append(f"| {selector}")
            
            line = " ".join(parts)
            lines.append(line)
            
            # 检查长度限制
            if len("\n".join(lines)) > max_chars:
                lines.append(f"... 还有 {len(elements) - idx - 1} 个元素未显示")
                break
        
        return "\n".join(lines)

    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
