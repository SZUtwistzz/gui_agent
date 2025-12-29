# 架构说明

## 项目结构

```
lightweight_agent/
├── __init__.py          # 包初始化，导出主要类
├── agent.py             # Agent 核心类 - 任务执行循环
├── browser.py           # Browser 控制类 - 基于 Playwright
├── tools.py             # 工具集 - 定义可执行的操作
├── llm.py               # LLM 接口封装 - OpenAI/Anthropic/豆包
├── example_doubao.py    # 豆包模型使用示例
├── test_llm_comparison.py  # LLM 对比测试框架
├── web_server.py        # Web GUI 服务器 - FastAPI + WebSocket
├── run_web.py           # Web 服务器启动脚本
├── example.py           # 使用示例
├── pyproject.toml       # 项目配置和依赖
├── README.md            # 项目说明
├── QUICKSTART.md        # 快速开始指南
├── ARCHITECTURE.md      # 架构说明（本文件）
└── static/
    └── index.html       # Web GUI 前端界面
```

## 核心组件

### 1. Agent (`agent.py`)

Agent 是系统的核心，负责：
- 接收任务描述
- 与 LLM 交互，理解任务并决定下一步操作
- 调用工具执行操作
- 维护执行历史
- 循环执行直到任务完成或达到最大步数

**关键方法：**
- `run()` - 执行任务的主循环
- `_parse_action()` - 从 LLM 响应中解析操作
- `_build_system_prompt()` - 构建系统提示

### 2. Browser (`browser.py`)

Browser 封装了 Playwright，提供浏览器控制能力：
- 启动/关闭浏览器
- 页面导航
- 元素操作（点击、输入）
- 页面信息获取（HTML、标题、URL）
- 元素查找和信息提取

**关键方法：**
- `start()` - 启动浏览器
- `navigate()` - 导航到 URL
- `click()` - 点击元素
- `fill()` - 填充输入框
- `get_elements_info()` - 获取可交互元素列表

### 3. Tools (`tools.py`)

Tools 定义了 Agent 可以执行的所有操作：
- `navigate` - 导航到 URL
- `click` - 点击元素
- `input` - 输入文本
- `extract` - 提取页面内容
- `screenshot` - 截图
- `get_elements` - 获取元素列表
- `done` - 完成任务

每个工具返回 `ActionResult`，包含执行结果和状态。

### 4. LLM (`llm.py`)

LLM 模块提供了统一的 LLM 接口：
- `BaseLLM` - 基类
- `ChatOpenAI` - OpenAI GPT 接口
- `ChatAnthropic` - Anthropic Claude 接口
- `ChatDoubao` - 豆包 Seed1.8 接口

所有 LLM 实现都遵循相同的接口，可以轻松切换。支持通过环境变量或直接传入 API key 进行配置。

### 5. Web Server (`web_server.py`)

Web 服务器提供：
- HTTP 接口提供 Web GUI
- WebSocket 接口实现实时通信
- 任务管理和状态更新

**关键端点：**
- `GET /` - 返回 Web GUI 页面
- `WebSocket /ws` - 实时通信通道

## 执行流程

```
1. 用户输入任务
   ↓
2. Agent 初始化（Browser + LLM + Tools）
   ↓
3. Agent.run() 开始执行循环
   ↓
4. 获取当前页面状态
   ↓
5. 构建消息（系统提示 + 历史 + 当前状态）
   ↓
6. 调用 LLM 获取下一步操作
   ↓
7. 解析 LLM 响应，提取操作（JSON 格式）
   ↓
8. 调用 Tools.execute() 执行操作
   ↓
9. 更新消息历史，继续循环
   ↓
10. 直到任务完成（调用 done）或达到最大步数
```

## 与 browser-use 的对比

### 相似点
- 核心思想：使用 LLM 理解任务并执行浏览器操作
- Agent 循环：任务 -> LLM 决策 -> 执行 -> 反馈 -> 循环
- 工具系统：可扩展的工具注册表

### 不同点

| 特性 | browser-use | lightweight-agent |
|------|-------------|-------------------|
| 浏览器控制 | CDP (Chrome DevTools Protocol) | Playwright |
| 架构复杂度 | 高（事件系统、CDP 管理） | 低（直接 API 调用）|
| Web GUI | 无 | 有（FastAPI + WebSocket）|
| DOM 处理 | 复杂的 DOM 树分析 | 简单的元素查找 |
| 工具数量 | 20+ | 7 个核心工具 |
| 代码量 | ~10k+ 行 | ~500 行 |
| 学习曲线 | 陡峭 | 平缓 |

## 扩展建议

### 添加新工具

在 `tools.py` 中添加：

```python
async def _my_tool(self, param1: str, param2: int) -> ActionResult:
    """我的自定义工具"""
    try:
        # 实现工具逻辑
        result = await self.browser.some_operation(param1, param2)
        return ActionResult(success=True, content=str(result))
    except Exception as e:
        return ActionResult(success=False, error=str(e))

# 在 __init__ 中注册
self.tools["my_tool"] = self._my_tool
```

### 添加新的 LLM 提供商

在 `llm.py` 中添加：

```python
class ChatMyLLM(BaseLLM):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("MYLLM_API_KEY")
        if not self.api_key:
            raise ValueError("需要提供 MYLLM_API_KEY 或设置环境变量")
        super().__init__(self.api_key)
        # 初始化客户端
    
    async def chat(self, messages: List[Message]) -> str:
        # 实现 API 调用
        # 返回模型生成的文本
        pass
```

然后在 `web_server.py` 的 `create_llm()` 函数中添加新模型的支持。

### 改进 Agent 决策

修改 `agent.py` 中的：
- `_build_system_prompt()` - 改进系统提示
- `_parse_action()` - 改进操作解析逻辑
- 添加更多上下文信息到消息中

## 性能优化建议

1. **缓存页面状态** - 避免重复获取页面信息
2. **批量操作** - 支持一次执行多个操作
3. **智能重试** - 操作失败时自动重试
4. **元素定位优化** - 改进选择器匹配算法
5. **LLM 响应缓存** - 缓存相似的 LLM 响应

## 安全考虑

1. **API Key 保护** - 不要在代码中硬编码 API Key
2. **输入验证** - 验证用户输入的任务描述
3. **资源限制** - 限制最大执行时间和步数
4. **沙箱环境** - 考虑在容器中运行浏览器

