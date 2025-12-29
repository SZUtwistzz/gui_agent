# 快速开始指南

## 安装步骤

### 1. 安装依赖

```bash
cd lightweight_agent
pip install -e .
playwright install chromium
```

### 2. 配置 API Key

创建 `.env` 文件：

```bash
# 选择其中一个或多个 LLM 提供商
OPENAI_API_KEY=your-openai-key
# 或
ANTHROPIC_API_KEY=your-anthropic-key
# 或
DOUBAO_API_KEY=your-doubao-api-key
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3  # 可选，默认值
```

### 3. 启动方式

#### 方式一：Web GUI（推荐）

```bash
python run_web.py
```

然后在浏览器中打开 `http://localhost:8000`

#### 方式二：命令行示例

```bash
# 使用 OpenAI
python example.py

# 使用豆包 Seed1.8
python example_doubao.py
```

## 使用示例

### Web GUI 使用

1. 启动服务器后，在浏览器中打开 `http://localhost:8000`
2. 输入任务描述，例如：
   - "搜索 Python 教程并提取前 3 个结果的标题"
   - "访问 GitHub 并搜索 browser-use 项目"
   - "打开百度，搜索'人工智能'，然后告诉我前 5 个搜索结果"
3. 选择 LLM 提供商（OpenAI、Anthropic 或豆包 Seed1.8）
4. 如果需要，输入 API Key（否则使用环境变量中的配置）
5. 点击"开始任务"
6. 实时查看执行日志和浏览器操作

### 代码使用

```python
import asyncio
from dotenv import load_dotenv
from agent import Agent
from browser import Browser
from llm import ChatOpenAI, ChatDoubao

# 加载环境变量
load_dotenv()

async def main():
    browser = Browser(headless=False)
    
    # 使用 OpenAI（从环境变量读取 API key）
    llm = ChatOpenAI()
    
    # 或使用豆包 Seed1.8
    # llm = ChatDoubao()
    
    agent = Agent(
        task="搜索 Python 教程",
        llm=llm,
        browser=browser
    )
    
    result = await agent.run()
    print(result)

asyncio.run(main())
```

## 常见问题

### Q: 浏览器没有启动？

A: 确保已安装 Playwright 浏览器：
```bash
playwright install chromium
```

### Q: API Key 错误？

A: 确保在 `.env` 文件中设置了正确的 API Key，或者通过 Web GUI 界面输入。

### Q: 任务执行失败？

A: 
- 检查网络连接
- 确保任务描述清晰明确
- 查看日志中的错误信息
- 尝试增加 `max_steps` 参数

### Q: 如何停止任务？

A: 在 Web GUI 中点击"停止任务"按钮，或关闭浏览器窗口。

## 下一步

- 查看 `README.md` 了解详细功能
- 查看 `example.py` 和 `example_doubao.py` 了解代码示例
- 运行 `python test_llm_comparison.py` 对比不同 LLM 的表现
- 修改 `tools.py` 添加自定义工具
- 修改 `agent.py` 自定义 Agent 行为

