"""Agent 核心类 - 任务执行循环（支持多模态）"""

import json
import logging
import re
from typing import Optional, List, Dict, Any
try:
    from .browser import Browser
    from .llm import BaseLLM, Message, TextContent, ImageContent
    from .tools import Tools, ActionResult
except ImportError:
    from browser import Browser
    from llm import BaseLLM, Message, TextContent, ImageContent
    from tools import Tools, ActionResult

logger = logging.getLogger(__name__)


class Agent:
    """简化的 Agent 类 - 支持多模态视觉"""
    
    def __init__(
        self,
        task: str,
        llm: BaseLLM,
        browser: Optional[Browser] = None,
        max_steps: int = 500,
        use_vision: bool = True,  # 是否使用视觉能力
        use_dom_pruning: bool = True,  # 是否使用 DOM 剪枝
        max_elements: int = 40,  # 最大元素数量
    ):
        """
        初始化 Agent
        
        Args:
            task: 任务描述
            llm: LLM 实例
            browser: 浏览器实例（可选，会自动创建）
            max_steps: 最大执行步数
            use_vision: 是否使用视觉能力（需要 LLM 支持）
            use_dom_pruning: 是否使用 DOM 剪枝
            max_elements: 剪枝后最大保留元素数量
        """
        self.task = task
        self.llm = llm
        self.max_steps = max_steps
        self.browser = browser or Browser(headless=False)
        self.tools = Tools(self.browser)
        self.history: List[Dict[str, Any]] = []
        self.current_step = 0
        
        # 多模态配置
        self.use_vision = use_vision and getattr(llm, 'supports_vision', False)
        self.use_dom_pruning = use_dom_pruning
        self.max_elements = max_elements
        
        if self.use_vision:
            logger.info("✨ 多模态视觉模式已启用")
        else:
            logger.info("📝 纯文本模式（LLM 不支持视觉或已禁用）")
        
        if self.use_dom_pruning:
            logger.info(f"🌳 DOM 剪枝已启用（最多 {max_elements} 个元素）")
        
        # 任务进度跟踪
        self.completed_items: List[str] = []  # 已完成的项目
        self.selected_parts: Dict[str, Dict[str, Any]] = {}  # 已选择的配件 {类型: {名称, 价格}}
        
    async def run(self) -> Dict[str, Any]:
        """执行任务（支持多模态）"""
        await self.browser.start()
        
        try:
            # 构建系统提示
            system_prompt = self._build_system_prompt()
            messages: List[Message] = [
                Message(role="system", content=system_prompt),
            ]
            
            # 获取初始页面状态并创建第一条用户消息
            initial_state = await self._get_page_state()
            initial_message = await self._create_user_message(
                f"任务: {self.task}\n\n请开始执行任务。",
                initial_state
            )
            messages.append(initial_message)
            
            # 执行循环
            for step in range(self.max_steps):
                self.current_step = step + 1
                logger.info(f"步骤 {self.current_step}/{self.max_steps}")
                
                # 获取当前页面状态
                try:
                    current_url = await self.browser.get_url()
                    current_title = await self.browser.get_title()
                    page_info = f"当前页面: {current_title} ({current_url})"
                except:
                    page_info = "页面信息获取失败"
                
                # 调用 LLM 获取下一步操作
                response = await self.llm.chat(messages)
                logger.info(f"LLM 响应: {response[:200]}...")
                
                # 解析 LLM 响应，提取 JSON 格式的操作
                action = self._parse_action(response)
                
                if not action:
                    # 如果无法解析，尝试让 LLM 重新生成
                    messages.append(Message(role="assistant", content=response))
                    messages.append(Message(
                        role="user",
                        content="请以 JSON 格式返回操作，格式: {\"action\": \"工具名\", \"params\": {...}}"
                    ))
                    continue
                
                # 记录操作
                step_info = {
                    "step": self.current_step,
                    "action": action,
                    "page_info": page_info,
                    "llm_response": response
                }
                self.history.append(step_info)
                
                # 执行操作
                if action.get("action") == "done":
                    result = await self.tools.execute("done", {"result": action.get("params", {}).get("result", "任务完成")})
                    step_info["result"] = result.dict()
                    if result.is_done:
                        logger.info("任务完成！")
                        break
                else:
                    result = await self.tools.execute(
                        action["action"],
                        action.get("params", {})
                    )
                    step_info["result"] = result.dict()
                    
                    # 如果操作失败，记录错误
                    if not result.success:
                        messages.append(Message(role="assistant", content=response))
                        messages.append(Message(
                            role="user",
                            content=f"操作失败: {result.error}\n请尝试其他方法。"
                        ))
                    else:
                        # 操作成功，更新上下文
                        messages.append(Message(role="assistant", content=response))
                        
                        # 尝试更新已选配件（用于 PC 配置任务）
                        try:
                            self._update_selected_parts(response, result.content or "")
                        except Exception as e:
                            logger.debug(f"更新配件信息失败（可忽略）: {e}")
                        
                        # 构建进度提示
                        progress_info = self._build_progress_info()
                        
                        # 每 10 步提供一次总结
                        step_reminder = ""
                        if self.current_step % 10 == 0:
                            step_reminder = f"\n\n⏱️ 已执行 {self.current_step} 步，请确保任务正在正确进行。"
                        
                        # 构建任务完成检查提示
                        completion_check = self._build_completion_check_prompt()
                        
                        # 获取新的页面状态
                        new_state = await self._get_page_state()
                        
                        # 构建反馈消息
                        feedback_text = f"""操作成功: {result.content}
{page_info}

{progress_info}{step_reminder}

{completion_check}

⚠️ 重要提醒：
- 只有当所有任务目标都已达成时，才能调用 done()
- 调用 done() 必须提供详细的结果总结
- 不要重复已完成的操作！"""
                        
                        # 创建多模态消息
                        user_message = await self._create_user_message(feedback_text, new_state)
                        messages.append(user_message)
            
            return {
                "success": True,
                "history": self.history,
                "final_result": self.history[-1].get("result", {}).get("content") if self.history else None
            }
            
        except Exception as e:
            logger.error(f"Agent 执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "history": self.history
            }
        finally:
            # 不自动关闭浏览器，让用户查看结果
            # await self.browser.close()
            pass
    
    async def _get_page_state(self) -> Dict[str, Any]:
        """获取当前页面状态（用于多模态）"""
        if self.use_dom_pruning:
            # 使用剪枝后的 DOM 和截图
            state = await self.browser.get_compact_state(
                include_screenshot=self.use_vision,
                screenshot_quality=50,  # 中等质量
                max_elements=self.max_elements
            )
        else:
            # 传统方式
            state = {
                "url": await self.browser.get_url(),
                "title": await self.browser.get_title(),
                "elements": await self.browser.get_elements_info(),
                "screenshot": None
            }
            if self.use_vision:
                state["screenshot"] = await self.browser.screenshot()
        
        return state
    
    async def _create_user_message(self, text: str, page_state: Dict[str, Any]) -> Message:
        """创建用户消息（支持多模态）"""
        # 构建页面状态文本
        elements = page_state.get("elements", [])
        
        if self.use_dom_pruning and elements:
            # 格式化元素列表
            elements_text = self.browser.format_elements_for_llm(elements, max_chars=2500)
            full_text = f"{text}\n\n{elements_text}"
        else:
            full_text = text
        
        # 检查是否使用视觉
        screenshot = page_state.get("screenshot") if self.use_vision else None
        
        if screenshot and self.use_vision:
            # 创建多模态消息
            return Message.create_multimodal(
                role="user",
                text=full_text,
                image_data=screenshot,
                media_type="image/jpeg"
            )
        else:
            # 纯文本消息
            return Message(role="user", content=full_text)
    
    def _build_progress_info(self) -> str:
        """构建当前进度信息"""
        if not self.selected_parts:
            return "【当前进度】尚未选择任何配件"
        
        lines = ["【当前进度 - 已选配件】（不要重复选择这些！）"]
        total_price = 0
        for part_type, info in self.selected_parts.items():
            price = info.get('price', 0)
            total_price += price
            lines.append(f"  ✅ {part_type}: {info.get('name', '未知')} - ${price:.2f}")
        
        lines.append(f"  💰 当前总价: ${total_price:.2f}")
        
        # 列出还需要选择的配件
        all_parts = ["CPU", "CPU Cooler", "Motherboard", "Memory", "Storage", "Video Card", "Case", "Power Supply"]
        remaining = [p for p in all_parts if p not in self.selected_parts]
        if remaining:
            lines.append(f"  ⏳ 待选配件: {', '.join(remaining)}")
        else:
            lines.append("  🎉 所有配件已选择完成！请调用 done() 汇总结果")
        
        return "\n".join(lines)
    
    def _build_completion_check_prompt(self) -> str:
        """构建任务完成检查提示"""
        # 分析任务类型
        task_lower = self.task.lower()
        
        # 检查是否是 PC 配置任务
        if any(keyword in task_lower for keyword in ["配置", "电脑", "pc", "computer", "build", "配件"]):
            all_parts = ["CPU", "CPU Cooler", "Motherboard", "Memory", "Storage", "Video Card", "Case", "Power Supply"]
            remaining = [p for p in all_parts if p not in self.selected_parts]
            
            if remaining:
                return f"""【任务完成检查】
❌ 任务尚未完成！还有 {len(remaining)} 个配件未选择: {', '.join(remaining)}
请继续选择下一个配件，不要调用 done()！"""
            else:
                return """【任务完成检查】
✅ 所有配件已选择完成！
现在请调用 done() 并提供完整的配置单总结，包括：
- 所有选择的配件及其价格
- 总价格
- 配置单链接（如果有）"""
        
        # 检查是否是搜索/提取任务
        elif any(keyword in task_lower for keyword in ["搜索", "查找", "找到", "search", "find", "提取", "获取"]):
            return """【任务完成检查】
请确认：
1. 是否已找到所需的信息？
2. 是否已提取/保存了结果？
如果是，请调用 done() 并提供详细的搜索结果总结。
如果否，请继续执行搜索操作。"""
        
        # 通用任务
        else:
            return """【任务完成检查】
请根据原始任务目标检查：
1. 任务的主要目标是否已达成？
2. 是否有遗漏的步骤？
如果任务已完成，请调用 done() 并提供详细的结果总结。
如果还有未完成的步骤，请继续执行。"""
    
    def _update_selected_parts(self, response: str, result_content: str):
        """从响应中提取并更新已选配件"""
        # 配件类型关键词映射
        part_keywords = {
            "CPU": ["cpu", "processor", "ryzen", "intel core", "i5", "i7", "i9", "r5", "r7", "r9"],
            "CPU Cooler": ["cooler", "cooling", "aio", "水冷", "散热"],
            "Motherboard": ["motherboard", "主板", "b650", "x670", "z790", "b760"],
            "Memory": ["memory", "ram", "内存", "ddr4", "ddr5"],
            "Storage": ["storage", "ssd", "nvme", "硬盘", "固态"],
            "Video Card": ["video card", "gpu", "graphics", "显卡", "rtx", "rx", "geforce", "radeon"],
            "Case": ["case", "机箱", "itx case", "atx case"],
            "Power Supply": ["power supply", "psu", "电源", "watt"],
        }
        
        combined_text = (response + " " + result_content).lower()
        
        # 检测是否在选择某个配件
        for part_type, keywords in part_keywords.items():
            if part_type in self.selected_parts:
                continue  # 已选择的跳过
            
            for keyword in keywords:
                if keyword in combined_text and ("add" in combined_text or "select" in combined_text or "chose" in combined_text or "选择" in combined_text):
                    # 尝试提取价格
                    import re
                    price_match = re.search(r'\$(\d+(?:\.\d{2})?)', result_content)
                    price = float(price_match.group(1)) if price_match else 0
                    
                    # 提取名称（简化处理）
                    name = f"已选择的{part_type}"
                    
                    self.selected_parts[part_type] = {"name": name, "price": price}
                    logger.info(f"📦 已记录配件: {part_type} - ${price}")
                    break
    
    def _build_system_prompt(self) -> str:
        """构建系统提示"""
        # 视觉能力说明
        vision_info = ""
        if self.use_vision:
            vision_info = """
### 🖼️ 视觉能力（已启用）
你可以看到页面的截图！利用视觉信息来：
- 理解页面布局和设计
- 识别按钮、链接、输入框的位置
- 确认操作是否成功
- 发现页面上的关键信息

截图中的元素与元素列表中的 idx 对应，可以通过 pos 坐标定位。
"""
        
        # DOM 剪枝说明
        dom_info = ""
        if self.use_dom_pruning:
            dom_info = """
### 🌳 元素索引系统
页面元素已被智能剪枝和索引：
- [idx] 是元素的唯一索引号
- 使用 selector 字段的值来操作元素
- 元素按页面位置排序（从上到下，从左到右）
- 视口内的元素优先显示

操作示例：
- 点击索引为 5 的按钮：`{"action": "click", "params": {"selector": "#submit-btn"}}`
- 使用 data-agent-idx：`{"action": "click", "params": {"selector": "[data-agent-idx=\\"5\\"]"}}`
"""
        
        return f"""你是一个专业的浏览器自动化 Agent，能够通过工具操作浏览器完成复杂任务。

{self.tools.get_tools_description()}

## 重要提示
{vision_info}
{dom_info}
### 基本规则
1. 每次响应必须返回一个 JSON 格式的操作
2. **浏览器启动时是空白页（about:blank），你必须首先使用 navigate() 导航到目标网站！**
3. 如果操作失败，尝试其他方法
4. 优先使用元素列表中提供的 selector，如果不行再尝试其他选择器

### ⚠️ 任务完成规则（极其重要！）
1. **只有当任务的所有目标都已达成时，才能调用 done() 工具**
2. **调用 done() 时，必须在 result 参数中提供详细的结果总结**
3. **每个步骤完成后说"步骤X完成"，但这不意味着整个任务完成**
4. **不要在中间步骤调用 done()，必须完成所有步骤后才能调用**

正确的 done() 调用格式：
```json
{{
    "action": "done",
    "params": {{
        "result": "任务已全部完成！\\n\\n【结果总结】\\n- 完成项1: xxx\\n- 完成项2: xxx\\n\\n【详细信息】\\n..."
    }}
}}
```

错误示例（不要这样做）：
- ❌ 在第一步完成后就调用 done()
- ❌ 只是说"继续下一步"然后调用 done()  
- ❌ 没有提供具体结果就调用 done()

### 常用网站
- 中国电商: https://www.jd.com (京东), https://www.taobao.com (淘宝)
- 搜索引擎: https://www.baidu.com, https://www.bing.com, https://www.google.com
- 海外电商: https://www.amazon.com, https://www.newegg.com
- PC配件: https://pcpartpicker.com

### 处理人机验证/CAPTCHA/Cloudflare
- 如果页面标题是 "Just a moment..." 或页面内容包含 "Verify you are human"、"checking your browser" 等
- 这是 Cloudflare 人机验证，请调用 wait_for_user("请在浏览器中完成Cloudflare人机验证")
- 等待用户完成验证后，会自动刷新页面
- 验证完成后检查页面是否正常加载，如果仍显示验证页面，可再次调用 wait_for_user
- 如果多次验证失败，可以尝试 reload() 刷新页面

## 🖥️ PC 配置任务专用指南（PCPartPicker）

### 配件选择顺序（必须按此顺序）
1. **CPU** - 首先选择处理器
2. **CPU Cooler** - 选择散热器（水冷/风冷）
3. **Motherboard** - 选择主板（注意兼容性）
4. **Memory** - 选择内存
5. **Storage** - 选择存储（SSD）
6. **Video Card** - 选择显卡
7. **Case** - 选择机箱（ITX/ATX）
8. **Power Supply** - 选择电源

### ⚠️ 关键规则
- **每个配件只选择一次！选好后立即进入下一个配件类型**
- **不要返回已经选过的配件页面！**
- 选择配件后，点击 "Add" 或 "Choose" 按钮添加到配置单
- 添加成功后，立即进入下一个配件类别
- 每添加完一个配件，检查页面是否显示 "Part Added" 或类似确认信息

### PCPartPicker 操作流程
1. 导航到 https://pcpartpicker.com/list/
2. 点击 "Choose A CPU" 开始选择
3. 在配件页面，使用筛选和排序找到合适的配件
4. 点击配件旁边的 "Add" 按钮
5. 添加成功后，回到配置单页面
6. 继续选择下一个配件类型
7. 所有配件选完后，提取最终配置单和总价

### 工作流程建议
1. 先用 navigate() 打开目标网站
2. 用 get_elements() 或 get_text() 了解页面结构
3. 用 input() 填写搜索框，然后 click() 搜索按钮或 press_key("Enter")
4. 用 scroll() 滚动页面查看更多内容
5. 用 extract() 提取需要的信息（如价格、标题等）
6. 如需比较多个商品，可用 click() 进入详情页，然后 go_back() 返回
7. 完成后用 done() 汇总所有信息

当前任务: {self.task}
"""
    
    def _parse_action(self, response: str) -> Optional[Dict[str, Any]]:
        """从 LLM 响应中解析操作"""
        # 方法1：尝试提取代码块中的 JSON（优先）
        code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if code_block_match:
            try:
                action = json.loads(code_block_match.group(1))
                if "action" in action:
                    logger.info(f"从代码块解析到操作: {action}")
                    return self._validate_done_action(action, response)
            except json.JSONDecodeError:
                pass
        
        # 方法2：查找完整的 JSON 对象（支持嵌套）
        # 找到包含 "action" 的第一个 { 开始，然后匹配完整的 JSON
        action_pos = response.find('"action"')
        if action_pos != -1:
            # 向前找到最近的 {
            start = response.rfind('{', 0, action_pos)
            if start != -1:
                # 从 start 开始，匹配平衡的 {}
                depth = 0
                end = start
                for i, char in enumerate(response[start:], start):
                    if char == '{':
                        depth += 1
                    elif char == '}':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                
                if end > start:
                    json_str = response[start:end]
                    try:
                        action = json.loads(json_str)
                        if "action" in action:
                            logger.info(f"解析到操作: {action}")
                            return self._validate_done_action(action, response)
                    except json.JSONDecodeError as e:
                        logger.warning(f"JSON 解析失败: {e}, 字符串: {json_str[:100]}")
        
        # 方法3：检查是否是明确的任务完成声明
        # 必须同时满足: 明确表示任务完成 + 包含结果总结
        if self._is_explicit_task_completion(response):
            logger.info("检测到明确的任务完成声明")
            return {
                "action": "done",
                "params": {"result": response}
            }
        
        logger.warning(f"无法从响应中解析操作: {response[:200]}")
        return None
    
    def _validate_done_action(self, action: Dict[str, Any], response: str) -> Dict[str, Any]:
        """验证 done 操作是否合理"""
        if action.get("action") != "done":
            return action
        
        # 检查是否有明确的完成信号
        result = action.get("params", {}).get("result", "")
        combined_text = (response + " " + result).lower()
        
        # 检查是否包含任务完成的明确信号
        completion_signals = [
            "任务完成", "任务已完成", "已完成任务", "完成了任务",
            "task complete", "task completed", "task is done", "task finished",
            "all done", "任务结束", "执行完毕", "全部完成",
            "successfully completed", "成功完成"
        ]
        
        has_completion_signal = any(signal in combined_text for signal in completion_signals)
        
        # 检查是否有明确的结果描述
        result_signals = [
            "结果", "总结", "汇总", "配置", "价格", "result", "summary", 
            "找到", "获取", "提取", "selected", "chosen", "final"
        ]
        has_result = any(signal in combined_text for signal in result_signals)
        
        # 如果既没有完成信号也没有结果描述，可能是误判
        if not has_completion_signal and not has_result:
            logger.warning(f"done 操作缺少明确的完成信号或结果描述，可能是误判")
            # 但仍然返回，因为 LLM 明确调用了 done
        
        return action
    
    def _is_explicit_task_completion(self, response: str) -> bool:
        """检查响应是否是明确的任务完成声明"""
        response_lower = response.lower()
        
        # 必须包含的强完成信号（明确表示整个任务完成）
        strong_completion_patterns = [
            "任务全部完成", "任务已全部完成", "所有任务完成", "任务执行完毕",
            "task is fully complete", "all tasks completed", "task execution finished",
            "任务成功完成", "已成功完成所有", "完成了所有步骤"
        ]
        
        has_strong_signal = any(pattern in response_lower for pattern in strong_completion_patterns)
        
        # 弱完成信号（需要结合其他条件）
        weak_completion_signals = ["done", "完成", "finished", "completed"]
        has_weak_signal = any(signal in response_lower for signal in weak_completion_signals)
        
        # 排除信号（表示只是部分完成或进行中）
        exclusion_patterns = [
            "下一步", "继续", "接下来", "然后", "next step", "continue",
            "第一步完成", "第二步完成", "步骤完成", "已完成第",
            "部分完成", "正在进行", "还需要", "待处理"
        ]
        has_exclusion = any(pattern in response_lower for pattern in exclusion_patterns)
        
        # 结果汇总信号
        summary_signals = [
            "总结", "汇总", "最终结果", "配置单", "总价", "清单",
            "summary", "final result", "total price", "configuration"
        ]
        has_summary = any(signal in response_lower for signal in summary_signals)
        
        # 判断逻辑：
        # 1. 有强完成信号 且 无排除信号 -> 完成
        # 2. 有弱完成信号 且 有结果汇总 且 无排除信号 -> 完成
        if has_strong_signal and not has_exclusion:
            return True
        if has_weak_signal and has_summary and not has_exclusion:
            return True
        
        return False

