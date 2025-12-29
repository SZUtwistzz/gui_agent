"""测试豆包 API 配置

用于诊断和测试豆包 API 的连接和配置
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
import httpx

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

load_dotenv()

async def test_doubao_api():
    """测试豆包 API 连接"""
    
    api_key = os.getenv("DOUBAO_API_KEY")
    secret_key = os.getenv("DOUBAO_SECRET_KEY")
    base_url = os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    
    # 根据官方文档，使用 Access Key (API Key) 作为 Bearer token
    # Secret Key 可能需要用于签名，但 Bearer token 认证使用 Access Key
    auth_token = api_key or secret_key
    
    # 尝试多个可能的模型名称
    possible_models = [
        "doubao-seed-1-8-251215",  # 用户提供的
        "doubao-seed-1.8-251215",  # 带点号版本
        "doubao-seed-1.8",  # 简化版本
        "doubao-seed-1-8",  # 简化版本2
    ]
    
    if not auth_token:
        print("[错误] 未设置 DOUBAO_API_KEY 或 DOUBAO_SECRET_KEY")
        print("请在 .env 文件中设置: DOUBAO_SECRET_KEY=your-secret-key")
        print("或: DOUBAO_API_KEY=your-api-key")
        return
    
    print("=" * 60)
    print("豆包 API 配置测试")
    print("=" * 60)
    if api_key:
        print(f"API Key (Access Key): {api_key[:30]}... (使用作为 Bearer token)")
    elif secret_key:
        print(f"Secret Key: {secret_key[:30]}... (使用 Secret Key)")
    if secret_key:
        print(f"Secret Key: {secret_key[:30]}... (已配置，但未使用)")
    print(f"Base URL: {base_url}")
    print("=" * 60)
    print()
    
    # 测试消息
    test_messages = [
        {"role": "user", "content": "你好"}
    ]
    
    # 根据官方文档，使用标准端点
    endpoint = "/chat/completions"
    url = f"{base_url.rstrip('/')}{endpoint}"
    
    # 根据官方文档，使用 Bearer token 认证
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    }
    
    print(f"根据官方文档测试:")
    print(f"端点: {url}")
    if api_key:
        print(f"认证方式: Authorization: Bearer {api_key[:30]}... (Access Key)")
    elif secret_key:
        print(f"认证方式: Authorization: Bearer {secret_key[:30]}... (Secret Key)")
    print()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for model in possible_models:
            print(f"\n{'='*60}")
            print(f"测试模型: {model}")
            print(f"{'='*60}")
            
            payload = {
                "model": model,
                "messages": test_messages,
                "temperature": 0.7,
                "max_tokens": 100
            }
            
            try:
                print("发送请求...")
                response = await client.post(url, headers=headers, json=payload)
                
                print(f"状态码: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"\n[成功] API 调用成功!")
                    print(f"响应结构: {list(result.keys())}")
                    
                    if "choices" in result and len(result["choices"]) > 0:
                        content = result["choices"][0]["message"]["content"]
                        print(f"\n模型回复: {content[:200]}...")
                        print(f"\n✅ 找到可用的模型名称: {model}")
                        return True
                    else:
                        print(f"[警告] 响应格式异常，未找到 choices")
                        print(f"完整响应: {str(result)[:500]}")
                elif response.status_code == 401:
                    print(f"[错误] 401 - 认证失败")
                    print(f"请检查 API Key 是否正确")
                    print(f"响应: {response.text[:300]}")
                elif response.status_code == 404:
                    error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                    error_msg = error_data.get("error", {}).get("message", response.text[:200])
                    print(f"[错误] 404 - {error_msg}")
                elif response.status_code == 403:
                    print(f"[错误] 403 - 权限不足")
                    print(f"请检查 API Key 是否有权限访问该模型")
                    print(f"响应: {response.text[:300]}")
                else:
                    print(f"[错误] HTTP {response.status_code}")
                    error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                    if error_data:
                        error_msg = error_data.get("error", {}).get("message", "")
                        print(f"错误信息: {error_msg}")
                    else:
                        print(f"响应: {response.text[:500]}")
                    
            except httpx.TimeoutException:
                print(f"[错误] 请求超时")
                print(f"请检查网络连接")
            except Exception as e:
                print(f"[错误] 异常: {str(e)}")
                import traceback
                traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("所有测试都失败了。")
    print("\n建议:")
    print("1. 检查 API Key 是否正确")
    print("2. 检查 Base URL 是否正确")
    print("3. 查看豆包 API 文档确认正确的端点格式")
    print("4. 确认网络连接正常")
    print("=" * 60)
    return False

if __name__ == "__main__":
    asyncio.run(test_doubao_api())

