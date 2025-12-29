"""Web GUI 服务器"""

import asyncio
import json
import logging
import os
from typing import Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import uvicorn
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

try:
    from .agent import Agent
    from .browser import Browser
    from .llm import ChatOpenAI, ChatAnthropic, ChatDoubao, ChatDeepSeek, BaseLLM
except ImportError:
    from agent import Agent
    from browser import Browser
    from llm import ChatOpenAI, ChatAnthropic, ChatDoubao, ChatDeepSeek, BaseLLM

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="轻量级 Web GUI Agent")

# 存储活动的 Agent 实例
active_agents: Dict[str, Agent] = {}


def create_llm(llm_type: str = "openai", api_key: Optional[str] = None) -> BaseLLM:
    """创建 LLM 实例"""
    if llm_type == "openai":
        return ChatOpenAI(api_key=api_key)
    elif llm_type == "anthropic":
        return ChatAnthropic(api_key=api_key)
    elif llm_type == "doubao":
        return ChatDoubao(api_key=api_key)
    elif llm_type == "deepseek":
        return ChatDeepSeek(api_key=api_key)
    else:
        raise ValueError(f"不支持的 LLM 类型: {llm_type}")


@app.get("/", response_class=HTMLResponse)
async def get_index():
    """返回主页面"""
    html_path = Path(__file__).parent / "static" / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>轻量级 Web GUI Agent</title>
        <meta charset="utf-8">
    </head>
    <body>
        <h1>请创建 static/index.html 文件</h1>
    </body>
    </html>
    """)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点，用于实时通信"""
    await websocket.accept()
    agent_id = None
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")
            
            if msg_type == "start_task":
                # 开始新任务
                task = message.get("task", "")
                llm_type = message.get("llm_type", "openai")
                api_key = message.get("api_key")
                
                if not task:
                    await websocket.send_json({
                        "type": "error",
                        "message": "任务描述不能为空"
                    })
                    continue
                
                try:
                    # 创建 LLM
                    llm = create_llm(llm_type, api_key)
                    
                    # 创建浏览器和 Agent
                    # 检查是否使用连接模式（连接到已运行的Chrome）
                    use_existing_browser = message.get("use_existing_browser", False)
                    browser = Browser(
                        headless=False,
                        connect_to_existing=use_existing_browser
                    )
                    agent = Agent(task=task, llm=llm, browser=browser)
                    agent_id = f"agent_{id(agent)}"
                    active_agents[agent_id] = agent
                    
                    await websocket.send_json({
                        "type": "task_started",
                        "agent_id": agent_id,
                        "message": "任务已开始"
                    })
                    
                    # 在后台执行任务
                    asyncio.create_task(run_agent_with_updates(agent, agent_id, websocket))
                    
                except Exception as e:
                    logger.error(f"启动任务失败: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"启动任务失败: {str(e)}"
                    })
            
            elif msg_type == "stop_task":
                # 停止任务
                if agent_id and agent_id in active_agents:
                    # 这里可以实现停止逻辑
                    await websocket.send_json({
                        "type": "task_stopped",
                        "message": "任务已停止"
                    })
            
            elif msg_type == "get_status":
                # 获取状态
                if agent_id and agent_id in active_agents:
                    agent = active_agents[agent_id]
                    await websocket.send_json({
                        "type": "status",
                        "step": agent.current_step,
                        "history": agent.history[-5:] if agent.history else []
                    })
    
    except WebSocketDisconnect:
        logger.info("WebSocket 连接断开")
        if agent_id and agent_id in active_agents:
            # 清理资源
            agent = active_agents[agent_id]
            try:
                await agent.browser.close()
            except:
                pass
            del active_agents[agent_id]


async def run_agent_with_updates(agent: Agent, agent_id: str, websocket: WebSocket):
    """运行 Agent 并发送更新"""
    try:
        async def run_with_updates():
            await agent.browser.start()
            
            try:
                system_prompt = agent._build_system_prompt()
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"任务: {agent.task}\n\n请开始执行任务。"}
                ]
                
                for step in range(agent.max_steps):
                    agent.current_step = step + 1
                    
                    # 发送步骤开始通知
                    try:
                        current_url = await agent.browser.get_url()
                        current_title = await agent.browser.get_title()
                        page_info = f"{current_title} ({current_url})"
                    except:
                        page_info = "获取页面信息中..."
                    
                    await websocket.send_json({
                        "type": "step_start",
                        "step": agent.current_step,
                        "page_info": page_info
                    })
                    
                    # 调用 LLM
                    try:
                        from .llm import Message
                    except ImportError:
                        from llm import Message
                    llm_messages = [Message(role=msg["role"], content=msg["content"]) for msg in messages]
                    response = await agent.llm.chat(llm_messages)
                    
                    await websocket.send_json({
                        "type": "llm_response",
                        "step": agent.current_step,
                        "response": response[:500]  # 限制长度
                    })
                    
                    # 解析和执行操作
                    action = agent._parse_action(response)
                    
                    if not action:
                        messages.append({"role": "assistant", "content": response})
                        messages.append({
                            "role": "user",
                            "content": "请以 JSON 格式返回操作，格式: {\"action\": \"工具名\", \"params\": {...}}"
                        })
                        continue
                    
                    await websocket.send_json({
                        "type": "action_executing",
                        "step": agent.current_step,
                        "action": action
                    })
                    
                    # 执行操作
                    if action.get("action") == "done":
                        result = await agent.tools.execute("done", {
                            "result": action.get("params", {}).get("result", "任务完成")
                        })
                        step_info = {
                            "step": agent.current_step,
                            "action": action,
                            "result": result.dict()
                        }
                        agent.history.append(step_info)
                        
                        await websocket.send_json({
                            "type": "step_complete",
                            "step": agent.current_step,
                            "action": action,
                            "result": result.dict()
                        })
                        
                        if result.is_done:
                            await websocket.send_json({
                                "type": "task_complete",
                                "result": result.content
                            })
                            break
                    else:
                        result = await agent.tools.execute(
                            action["action"],
                            action.get("params", {})
                        )
                        
                        step_info = {
                            "step": agent.current_step,
                            "action": action,
                            "result": result.dict()
                        }
                        agent.history.append(step_info)
                        
                        await websocket.send_json({
                            "type": "step_complete",
                            "step": agent.current_step,
                            "action": action,
                            "result": result.dict()
                        })
                        
                        # 更新消息历史
                        messages.append({"role": "assistant", "content": response})
                        if not result.success:
                            messages.append({
                                "role": "user",
                                "content": f"操作失败: {result.error}\n请尝试其他方法。"
                            })
                        else:
                            # 尝试更新已选配件
                            try:
                                agent._update_selected_parts(response, result.content or "")
                            except Exception:
                                pass
                            
                            # 构建进度提示
                            try:
                                progress_info = agent._build_progress_info()
                            except Exception:
                                progress_info = ""
                            
                            # 构建任务完成检查提示
                            try:
                                completion_check = agent._build_completion_check_prompt()
                            except Exception:
                                completion_check = "请检查任务是否已完成。"
                            
                            messages.append({
                                "role": "user",
                                "content": f"""操作成功: {result.content}
{page_info}

{progress_info}

{completion_check}

⚠️ 重要提醒：
- 只有当所有任务目标都已达成时，才能调用 done()
- 调用 done() 必须提供详细的结果总结
- 不要重复已完成的操作！"""
                            })
                
                await websocket.send_json({
                    "type": "task_max_steps",
                    "message": "任务执行结束（达到最大步数限制）",
                    "result": agent.history[-1].get("result", {}).get("content") if agent.history else None
                })
                
            except Exception as e:
                logger.error(f"Agent 执行错误: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"执行错误: {str(e)}"
                })
        
        await run_with_updates()
        
    except Exception as e:
        logger.error(f"运行 Agent 失败: {e}")
        await websocket.send_json({
            "type": "error",
            "message": f"运行失败: {str(e)}"
        })


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

