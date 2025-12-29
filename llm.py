"""LLM 接口封装"""

import os
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Message(BaseModel):
    """消息模型"""
    role: str  # "system", "user", "assistant"
    content: str


class BaseLLM:
    """LLM 基类"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        # 不在这里验证，让子类自己处理
    
    async def chat(self, messages: List[Message]) -> str:
        """发送消息并获取回复"""
        raise NotImplementedError


class ChatOpenAI(BaseLLM):
    """OpenAI ChatGPT 接口"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("需要提供 OPENAI_API_KEY 或设置环境变量")
        super().__init__(self.api_key)
        self.model = model
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=self.api_key)
        except ImportError:
            raise ImportError("请安装 openai: pip install openai")
    
    async def chat(self, messages: List[Message]) -> str:
        """调用 OpenAI API"""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": msg.role, "content": msg.content} for msg in messages],
                temperature=0.7,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API 调用失败: {e}")
            raise


class ChatAnthropic(BaseLLM):
    """Anthropic Claude 接口"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("需要提供 ANTHROPIC_API_KEY 或设置环境变量")
        super().__init__(self.api_key)
        self.model = model
        try:
            from anthropic import AsyncAnthropic
            self.client = AsyncAnthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError("请安装 anthropic: pip install anthropic")
    
    async def chat(self, messages: List[Message]) -> str:
        """调用 Anthropic API"""
        try:
            # Anthropic 需要 system 消息单独处理
            system_msg = None
            chat_messages = []
            
            for msg in messages:
                if msg.role == "system":
                    system_msg = msg.content
                else:
                    chat_messages.append({
                        "role": msg.role,
                        "content": msg.content
                    })
            
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_msg or "你是一个有用的 AI 助手。",
                messages=chat_messages,
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API 调用失败: {e}")
            raise


class ChatDeepSeek(BaseLLM):
    """DeepSeek 接口 (OpenAI 兼容)"""
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        model: str = "deepseek-chat",
        base_url: Optional[str] = None
    ):
        """
        初始化 DeepSeek 模型
        
        DeepSeek 使用 OpenAI 兼容的 API 格式
        - API 端点: https://api.deepseek.com/v1
        - 认证方式: Authorization: Bearer {API_KEY}
        
        Args:
            api_key: API密钥，也可通过环境变量 DEEPSEEK_API_KEY 设置
            model: 模型名称，默认为 deepseek-chat，可选 deepseek-reasoner
            base_url: API基础URL，默认为 https://api.deepseek.com/v1
        """
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("需要提供 DEEPSEEK_API_KEY 或设置环境变量")
        super().__init__(self.api_key)
        self.model = model
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        except ImportError:
            raise ImportError("请安装 openai: pip install openai")
    
    async def chat(self, messages: List[Message]) -> str:
        """调用 DeepSeek API"""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": msg.role, "content": msg.content} for msg in messages],
                temperature=0.7,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"DeepSeek API 调用失败: {e}")
            raise


class ChatDoubao(BaseLLM):
    """豆包 Seed1.8 接口"""
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        model: str = "doubao-seed-1-8-251215",
        base_url: Optional[str] = None
    ):
        """
        初始化豆包模型
        
        根据官方文档：
        - API 端点: https://ark.cn-beijing.volces.com/api/v3/chat/completions
        - 认证方式: Authorization: Bearer {API_KEY} 或使用 AK/SK
        
        Args:
            api_key: API密钥（Access Key），也可通过环境变量 DOUBAO_API_KEY 设置
            secret_key: Secret Access Key，也可通过环境变量 DOUBAO_SECRET_KEY 设置
            model: 模型名称，默认为 doubao-seed-1-8-251215
            base_url: API基础URL，默认为 https://ark.cn-beijing.volces.com/api/v3
        """
        # 获取 Access Key 和 Secret Key
        self.secret_key = secret_key or os.getenv("DOUBAO_SECRET_KEY")
        self.api_key = api_key or os.getenv("DOUBAO_API_KEY")
        
        # 根据官方文档，使用 Access Key (API Key) 作为 Bearer token
        # Secret Key 可能需要用于签名，但 Bearer token 认证使用 Access Key
        if self.api_key:
            self.auth_token = self.api_key
        elif self.secret_key:
            # 如果没有 API Key，尝试使用 Secret Key（虽然可能不正确）
            self.auth_token = self.secret_key
        else:
            raise ValueError("需要提供 DOUBAO_API_KEY 或设置环境变量")
        
        super().__init__(self.auth_token)
        self.model = model
        # 默认使用火山引擎的 API 端点，如果不对请通过环境变量或参数覆盖
        self.base_url = base_url or os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        try:
            import httpx
            self._client = None
        except ImportError:
            raise ImportError("请安装 httpx: pip install httpx")
    
    @property
    def client(self):
        """懒加载 httpx 客户端"""
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client
    
    async def chat(self, messages: List[Message]) -> str:
        """
        调用豆包 API
        
        根据官方文档：
        - 端点: POST https://ark.cn-beijing.volces.com/api/v3/chat/completions
        - 认证: Authorization: Bearer {API_KEY}
        - 响应格式: 类似 OpenAI，包含 choices 数组
        """
        import httpx
        
        # 转换消息格式
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # 构建请求头 - 根据官方文档使用 Bearer token
        # 使用 secret_key 或 api_key 作为 Bearer token
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.auth_token}"
        }
        
        # 构建请求体 - 根据官方文档格式
        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": 0.7,
            "max_tokens": 4096
        }
        
        # 根据官方文档，端点路径是 /chat/completions
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        
        try:
            logger.info(f"调用豆包 API: {url} (模型: {self.model})")
            
            response = await self.client.post(
                url,
                headers=headers,
                json=payload,
                timeout=60.0
            )
            
            # 处理响应
            response.raise_for_status()
            result = response.json()
            
            # 根据官方文档，响应格式包含 choices 数组
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            else:
                error_msg = f"API 响应格式错误，未找到 choices: {result}"
                logger.error(error_msg)
                raise ValueError(error_msg)
                
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response else str(e)
            error_msg = (
                f"豆包 API 调用失败 (HTTP {e.response.status_code})\n"
                f"URL: {url}\n"
                f"错误详情: {error_detail}\n\n"
                f"请检查:\n"
                f"1. DOUBAO_API_KEY 是否正确（当前: {self.api_key[:20]}...）\n"
                f"2. DOUBAO_BASE_URL 是否正确（当前: {self.base_url}）\n"
                f"3. 模型名称是否正确（当前: {self.model}）\n"
                f"4. API Key 是否有权限访问该模型\n"
                f"5. 网络连接是否正常"
            )
            logger.error(error_msg)
            raise ValueError(error_msg) from e
        except Exception as e:
            error_msg = f"豆包 API 调用异常: {str(e)}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e