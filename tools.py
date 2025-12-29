"""工具集 - 定义 Agent 可以执行的操作"""

import json
import logging
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
try:
    from .browser import Browser
except ImportError:
    from browser import Browser

logger = logging.getLogger(__name__)


class ActionResult(BaseModel):
    """操作结果"""
    success: bool = True
    content: Optional[str] = None
    error: Optional[str] = None
    is_done: bool = False


class Tools:
    """工具注册表"""
    
    def __init__(self, browser: Browser):
        self.browser = browser
        self.tools = {
            "navigate": self._navigate,
            "click": self._click,
            "input": self._input,
            "extract": self._extract,
            "screenshot": self._screenshot,
            "get_elements": self._get_elements,
            "scroll": self._scroll,
            "go_back": self._go_back,
            "press_key": self._press_key,
            "get_text": self._get_text,
            "wait": self._wait,
            "wait_for_user": self._wait_for_user,
            "reload": self._reload,
            "done": self._done,
        }
    
    def get_tools_description(self) -> str:
        """获取工具描述，用于 LLM prompt"""
        return """可用的工具：
1. navigate(url: str) - 导航到指定 URL
2. click(selector: str) - 点击页面元素，selector 可以是 CSS 选择器或 XPath
3. input(selector: str, text: str) - 在输入框中输入文本
4. extract(query: str) - 从页面提取信息，返回页面文本内容（用于获取商品价格、标题等）
5. screenshot() - 截取当前页面截图
6. get_elements() - 获取页面所有可交互元素列表
7. scroll(direction: str, amount: int) - 滚动页面，direction 可选 "up"/"down"/"left"/"right"，amount 为像素数(默认500)
8. go_back() - 返回上一页
9. press_key(key: str) - 按键，如 "Enter", "Tab", "Escape", "ArrowDown"
10. get_text() - 获取当前页面的纯文本内容（用于分析页面信息）
11. wait(seconds: int) - 等待指定秒数
12. wait_for_user(message: str) - 暂停执行，等待用户完成操作（如人机验证），message 是提示信息
13. reload() - 刷新当前页面（Cloudflare验证后可能需要刷新）
14. done(result: str) - 完成任务，result 是任务完成的结果描述

返回格式必须是 JSON：
{
    "action": "工具名称",
    "params": {"参数名": "参数值"}
}
"""
    
    async def execute(self, action: str, params: Dict[str, Any]) -> ActionResult:
        """执行工具"""
        logger.info(f"准备执行工具: {action}, 参数: {params}")
        
        if action not in self.tools:
            logger.error(f"未知的工具: {action}")
            return ActionResult(
                success=False,
                error=f"未知的工具: {action}"
            )
        
        try:
            result = await self.tools[action](**params)
            if isinstance(result, ActionResult):
                logger.info(f"工具 {action} 执行完成: success={result.success}, content={result.content[:100] if result.content else None}")
                return result
            logger.info(f"工具 {action} 执行完成: {str(result)[:100]}")
            return ActionResult(success=True, content=str(result))
        except Exception as e:
            logger.error(f"执行工具 {action} 失败: {e}", exc_info=True)
            return ActionResult(
                success=False,
                error=str(e)
            )
    
    async def _navigate(self, url: str) -> ActionResult:
        """导航工具"""
        try:
            await self.browser.navigate(url)
            # 检查是否遇到了人机验证
            page_text = await self.browser.get_text()
            title = await self.browser.get_title()
            
            # 检测常见的人机验证关键词
            captcha_keywords = ["captcha", "verify", "robot", "human", "challenge", 
                               "验证", "人机", "安全检查", "please wait", "checking"]
            page_lower = (page_text + title).lower()
            
            if any(keyword in page_lower for keyword in captcha_keywords):
                return ActionResult(
                    success=True,
                    content=f"已导航到 {url}，但检测到可能存在人机验证。建议调用 wait_for_user() 等待用户完成验证。"
                )
            
            return ActionResult(
                success=True,
                content=f"已导航到 {url}，页面标题: {title}"
            )
        except Exception as e:
            logger.error(f"导航到 {url} 失败: {e}")
            return ActionResult(
                success=False,
                error=f"导航失败: {e}"
            )
    
    async def _click(self, selector: str) -> ActionResult:
        """点击工具"""
        try:
            await self.browser.click(selector)
            # 等待页面加载
            await self.browser.page.wait_for_load_state("networkidle", timeout=5000)
            return ActionResult(
                success=True,
                content=f"已点击元素: {selector}"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"点击失败: {e}"
            )
    
    async def _input(self, selector: str, text: str) -> ActionResult:
        """输入工具"""
        try:
            await self.browser.fill(selector, text)
            return ActionResult(
                success=True,
                content=f"已在 {selector} 输入文本"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"输入失败: {e}"
            )
    
    async def _extract(self, query: str) -> ActionResult:
        """提取工具 - 获取页面内容用于分析"""
        try:
            title = await self.browser.get_title()
            url = await self.browser.get_url()
            
            # 获取页面纯文本内容
            text = await self.browser.get_text()
            
            # 限制文本长度，避免超出 LLM 上下文
            max_length = 8000
            if len(text) > max_length:
                text = text[:max_length] + "\n...(内容已截断)"
            
            content = f"""页面标题: {title}
URL: {url}

=== 页面内容 ===
{text}

=== 提取任务 ===
请根据以上页面内容，{query}"""
            
            return ActionResult(
                success=True,
                content=content
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"提取失败: {e}"
            )
    
    async def _screenshot(self) -> ActionResult:
        """截图工具"""
        try:
            screenshot_bytes = await self.browser.screenshot()
            return ActionResult(
                success=True,
                content="截图已保存"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"截图失败: {e}"
            )
    
    async def _get_elements(self) -> ActionResult:
        """获取元素列表（使用 DOM 剪枝）"""
        try:
            # 使用剪枝后的 DOM
            dom_info = await self.browser.get_pruned_dom(max_elements=50)
            elements = dom_info.get("elements", [])
            
            # 格式化为易读的文本
            formatted = self.browser.format_elements_for_llm(elements, max_chars=4000)
            
            return ActionResult(
                success=True,
                content=f"找到 {len(elements)} 个可交互元素:\n{formatted}"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"获取元素失败: {e}"
            )
    
    async def _scroll(self, direction: str = "down", amount: int = 500) -> ActionResult:
        """滚动页面"""
        try:
            await self.browser.scroll(direction, amount)
            return ActionResult(
                success=True,
                content=f"已向{direction}滚动 {amount} 像素"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"滚动失败: {e}"
            )
    
    async def _go_back(self) -> ActionResult:
        """返回上一页"""
        try:
            await self.browser.go_back()
            new_url = await self.browser.get_url()
            return ActionResult(
                success=True,
                content=f"已返回上一页: {new_url}"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"返回失败: {e}"
            )
    
    async def _press_key(self, key: str) -> ActionResult:
        """按键"""
        try:
            await self.browser.press_key(key)
            return ActionResult(
                success=True,
                content=f"已按键: {key}"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"按键失败: {e}"
            )
    
    async def _get_text(self) -> ActionResult:
        """获取页面纯文本（智能摘要）"""
        try:
            text = await self.browser.get_text()
            title = await self.browser.get_title()
            url = await self.browser.get_url()
            
            # 智能截取：保留开头和关键部分
            max_length = 4000
            if len(text) > max_length:
                # 保留开头 60% 和结尾 30%
                head_len = int(max_length * 0.6)
                tail_len = int(max_length * 0.3)
                text = text[:head_len] + "\n\n...(中间内容已省略)...\n\n" + text[-tail_len:]
            
            # 压缩多余空白
            import re
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = re.sub(r' {2,}', ' ', text)
            
            return ActionResult(
                success=True,
                content=f"页面: {title}\nURL: {url}\n\n{text}"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"获取文本失败: {e}"
            )
    
    async def _wait(self, seconds: int = 2) -> ActionResult:
        """等待指定秒数"""
        try:
            import asyncio
            await asyncio.sleep(seconds)
            return ActionResult(
                success=True,
                content=f"已等待 {seconds} 秒"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"等待失败: {e}"
            )
    
    async def _wait_for_user(self, message: str = "请在浏览器中完成操作") -> ActionResult:
        """暂停执行，等待用户完成操作（如人机验证）
        
        会等待45秒让用户完成验证，然后继续执行
        """
        try:
            import asyncio
            logger.info(f"⏸️ 暂停执行: {message}")
            logger.info("⏳ 等待用户完成操作（45秒）...")
            print("\n" + "="*50)
            print(f"🔔 {message}")
            print("⏳ 请在45秒内完成操作...")
            print("="*50 + "\n")
            
            # 等待45秒让用户完成验证
            await asyncio.sleep(45)
            
            # 刷新页面以确保获取最新状态
            try:
                await self.browser.reload()
                await asyncio.sleep(2)  # 等待页面加载
            except Exception:
                pass
            
            # 获取当前页面状态
            url = await self.browser.get_url()
            title = await self.browser.get_title()
            
            return ActionResult(
                success=True,
                content=f"用户操作完成。当前页面: {title} ({url})"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"等待用户操作失败: {e}"
            )
    
    async def _reload(self) -> ActionResult:
        """刷新当前页面"""
        try:
            await self.browser.reload()
            import asyncio
            await asyncio.sleep(2)  # 等待页面加载
            
            url = await self.browser.get_url()
            title = await self.browser.get_title()
            
            return ActionResult(
                success=True,
                content=f"页面已刷新。当前页面: {title} ({url})"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                error=f"刷新失败: {e}"
            )
    
    async def _done(self, result: str) -> ActionResult:
        """完成任务"""
        return ActionResult(
            success=True,
            content=result,
            is_done=True
        )

