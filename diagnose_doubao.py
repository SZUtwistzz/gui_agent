"""豆包 API 详细诊断工具"""

import asyncio
import os
import sys
from dotenv import load_dotenv
import httpx
import json

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

load_dotenv()

async def diagnose():
    """详细诊断豆包 API 配置"""
    
    api_key = os.getenv("DOUBAO_API_KEY")
    base_url = os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    model = "doubao-seed-1-8-251215"
    
    print("=" * 70)
    print("豆包 API 详细诊断")
    print("=" * 70)
    print(f"\n1. 配置检查:")
    print(f"   API Key: {api_key[:30]}..." if api_key else "   API Key: [未设置]")
    print(f"   API Key 长度: {len(api_key) if api_key else 0} 字符")
    print(f"   Base URL: {base_url}")
    print(f"   模型名称: {model}")
    
    if not api_key:
        print("\n[错误] 未设置 DOUBAO_API_KEY")
        return
    
    # 检查 API Key 格式
    print(f"\n2. API Key 格式检查:")
    if len(api_key) < 20:
        print(f"   [警告] API Key 长度较短，可能不正确")
    if "-" in api_key:
        print(f"   [信息] API Key 包含连字符，格式类似 UUID")
    print(f"   [信息] API Key 格式看起来正常")
    
    # 测试请求
    print(f"\n3. API 请求测试:")
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "你好"}],
        "temperature": 0.7,
        "max_tokens": 100
    }
    
    print(f"   请求 URL: {url}")
    print(f"   请求方法: POST")
    print(f"   请求头: Authorization: Bearer {api_key[:30]}...")
    print(f"   请求体: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            print(f"\n   发送请求...")
            response = await client.post(url, headers=headers, json=payload)
            
            print(f"\n4. 响应分析:")
            print(f"   状态码: {response.status_code}")
            print(f"   响应头:")
            for key, value in response.headers.items():
                if key.lower() in ['content-type', 'content-length', 'server', 'x-request-id']:
                    print(f"     {key}: {value}")
            
            # 解析响应
            try:
                error_data = response.json()
                print(f"\n   响应内容 (JSON):")
                print(f"   {json.dumps(error_data, ensure_ascii=False, indent=2)}")
                
                if "error" in error_data:
                    error_info = error_data["error"]
                    error_code = error_info.get("code", "")
                    error_msg = error_info.get("message", "")
                    
                    print(f"\n5. 错误分析:")
                    print(f"   错误代码: {error_code}")
                    print(f"   错误消息: {error_msg}")
                    
                    if "NotFound" in error_code or "404" in str(response.status_code):
                        print(f"\n   可能的原因:")
                        print(f"   1. 模型名称 '{model}' 不存在或已过期")
                        print(f"   2. API Key 没有权限访问该模型")
                        print(f"   3. 需要在豆包控制台开通该模型的访问权限")
                        print(f"   4. 模型名称格式不正确")
                        
                        print(f"\n   建议操作:")
                        print(f"   1. 登录豆包/火山引擎控制台")
                        print(f"   2. 检查 API Key 的权限设置")
                        print(f"   3. 查看可用的模型列表")
                        print(f"   4. 确认模型名称是否正确（注意大小写和连字符）")
                        print(f"   5. 检查是否需要开通该模型的访问权限或配额")
                        
            except Exception as e:
                print(f"\n   响应内容 (文本):")
                print(f"   {response.text[:500]}")
            
        except httpx.TimeoutException:
            print(f"\n[错误] 请求超时")
        except Exception as e:
            print(f"\n[错误] 请求异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    asyncio.run(diagnose())


















