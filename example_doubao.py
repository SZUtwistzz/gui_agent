"""豆包 Seed1.8 模型使用示例"""

import asyncio
import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

from agent import Agent
from browser import Browser
from llm import ChatDoubao


async def main():
    """使用豆包 Seed1.8 模型运行 Agent"""
    
    # 方式1: 使用环境变量
    # 设置环境变量: export DOUBAO_API_KEY=your-api-key
    # llm = ChatDoubao()
    
    # 方式2: 直接传入 API key
    api_key = os.getenv("DOUBAO_API_KEY")
    if not api_key:
        print("请设置环境变量 DOUBAO_API_KEY 或在代码中提供 API key")
        return
    
    llm = ChatDoubao(
        api_key=api_key,
        model="doubao-seed-1-8-251215",  # 使用正确的模型名称
        base_url="https://ark.cn-beijing.volces.com/api/v3"  # 可选，默认值
    )
    
    # 创建浏览器（headless=False 可以看到浏览器操作）
    browser = Browser(headless=False)
    
    # 创建 Agent
    agent = Agent(
        task="打开百度首页并搜索 'Python 教程'",
        llm=llm,
        browser=browser,
        max_steps=20
    )
    
    # 运行任务
    print("开始执行任务...")
    result = await agent.run()
    
    # 打印结果
    print("\n" + "="*60)
    print("任务执行结果:")
    print("="*60)
    print(f"成功: {result.get('success')}")
    print(f"总步数: {len(agent.history)}")
    if result.get('final_result'):
        print(f"最终结果: {result.get('final_result')}")
    if result.get('error'):
        print(f"错误: {result.get('error')}")
    
    # 打印执行历史
    print("\n执行历史:")
    for i, step in enumerate(agent.history, 1):
        print(f"\n步骤 {i}:")
        print(f"  操作: {step.get('action', {}).get('action')}")
        print(f"  结果: {step.get('result', {}).get('content', 'N/A')[:100]}")


if __name__ == "__main__":
    asyncio.run(main())

