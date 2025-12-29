"""使用示例"""

import asyncio
import os
from dotenv import load_dotenv
from agent import Agent
from browser import Browser
from llm import ChatOpenAI

load_dotenv()


async def main():
    """基本使用示例"""
    # 创建浏览器
    browser = Browser(headless=False)
    
    # 创建 LLM（使用环境变量中的 API key）
    llm = ChatOpenAI()
    
    # 创建 Agent
    agent = Agent(
        task="搜索 Python 教程并告诉我前 3 个结果的标题",
        llm=llm,
        browser=browser,
        max_steps=15
    )
    
    # 执行任务
    result = await agent.run()
    
    print("\n" + "="*50)
    print("任务执行结果:")
    print("="*50)
    print(f"成功: {result['success']}")
    if result.get('final_result'):
        print(f"最终结果: {result['final_result']}")
    print(f"\n执行了 {len(result['history'])} 个步骤")
    
    # 保持浏览器打开以便查看
    print("\n浏览器将保持打开状态，按 Enter 键关闭...")
    input()
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

