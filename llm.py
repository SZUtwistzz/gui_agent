"""LLM 接口封装 - 支持多模态"""

import os
import logging
import base64
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ImageContent(BaseModel):
    """图片内容"""
    type: str = "image"
    image_data: str  # base64 编码的图片数据
    media_type: str = "image/png"  # 图片类型


class TextContent(BaseModel):
    """文本内容"""
    type: str = "text"
    text: str


class Message(BaseModel):
    """消息模型 - 支持多模态"""
    role: str  # "system", "user", "assistant"
    content: Union[str, List[Union[TextContent, ImageContent]]]  # 支持纯文本或多模态内容
    
    def to_openai_format(self) -> Dict[str, Any]:
        """转换为 OpenAI API 格式"""
        if isinstance(self.content, str):
            return {"role": self.role, "content": self.content}
        
        # 多模态格式
        content_list = []
        for item in self.content:
            if isinstance(item, TextContent):
                content_list.append({"type": "text", "text": item.text})
            elif isinstance(item, ImageContent):
                content_list.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{item.media_type};base64,{item.image_data}",
                        "detail": "low"  # 使用 low 减少 token 消耗
                    }
                })
        return {"role": self.role, "content": content_list}
    
    def to_anthropic_format(self) -> Dict[str, Any]:
        """转换为 Anthropic API 格式"""
        if isinstance(self.content, str):
            return {"role": self.role, "content": self.content}
        
        # 多模态格式
        content_list = []
        for item in self.content:
            if isinstance(item, TextContent):
                content_list.append({"type": "text", "text": item.text})
            elif isinstance(item, ImageContent):
                content_list.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": item.media_type,
                        "data": item.image_data
                    }
                })
        return {"role": self.role, "content": content_list}
    
    @classmethod
    def create_multimodal(cls, role: str, text: str, image_data: Optional[bytes] = None, 
                          media_type: str = "image/png") -> "Message":
        """创建多模态消息的便捷方法"""
        if image_data is None:
            return cls(role=role, content=text)
        
        # 将图片转为 base64
        image_base64 = base64.b64encode(image_data).decode("utf-8")
        
        content = [
            TextContent(text=text),
            ImageContent(image_data=image_base64, media_type=media_type)
        ]
        return cls(role=role, content=content)


class BaseLLM:
    """LLM 基类"""
    
    supports_vision: bool = False  # 是否支持视觉/多模态
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        # 不在这里验证，让子类自己处理
    
    async def chat(self, messages: List[Message]) -> str:
        """发送消息并获取回复"""
        raise NotImplementedError


class ChatOpenAI(BaseLLM):
    """OpenAI ChatGPT 接口 - 支持多模态"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("需要提供 OPENAI_API_KEY 或设置环境变量")
        super().__init__(self.api_key)
        self.model = model
        self.supports_vision = True  # GPT-4o 系列支持视觉
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=self.api_key)
        except ImportError:
            raise ImportError("请安装 openai: pip install openai")
    
    async def chat(self, messages: List[Message]) -> str:
        """调用 OpenAI API（支持多模态）"""
        try:
            # 转换消息格式
            formatted_messages = [msg.to_openai_format() for msg in messages]
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=formatted_messages,
                temperature=0.7,
                max_tokens=4096,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API 调用失败: {e}")
            raise


class ChatAnthropic(BaseLLM):
    """Anthropic Claude 接口 - 支持多模态"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("需要提供 ANTHROPIC_API_KEY 或设置环境变量")
        super().__init__(self.api_key)
        self.model = model
        self.supports_vision = True  # Claude 3 系列支持视觉
        try:
            from anthropic import AsyncAnthropic
            self.client = AsyncAnthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError("请安装 anthropic: pip install anthropic")
    
    async def chat(self, messages: List[Message]) -> str:
        """调用 Anthropic API（支持多模态）"""
        try:
            # Anthropic 需要 system 消息单独处理
            system_msg = None
            chat_messages = []
            
            for msg in messages:
                if msg.role == "system":
                    # system 消息只能是纯文本
                    system_msg = msg.content if isinstance(msg.content, str) else msg.content[0].text
                else:
                    chat_messages.append(msg.to_anthropic_format())
            
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
    """DeepSeek 接口 (OpenAI 兼容) - 暂不支持多模态"""
    
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
        self.supports_vision = False  # DeepSeek 暂不支持视觉
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
        """调用 DeepSeek API（仅文本）"""
        try:
            # DeepSeek 不支持多模态，只提取文本内容
            formatted_messages = []
            for msg in messages:
                if isinstance(msg.content, str):
                    formatted_messages.append({"role": msg.role, "content": msg.content})
                else:
                    # 多模态消息，只提取文本
                    text_parts = [item.text for item in msg.content if isinstance(item, TextContent)]
                    formatted_messages.append({"role": msg.role, "content": "\n".join(text_parts)})
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=formatted_messages,
                temperature=0.7,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"DeepSeek API 调用失败: {e}")
            raise


class ChatDoubao(BaseLLM):
    """豆包 Seed1.8 接口 - 支持多模态"""
    
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
        self.supports_vision = True  # 豆包支持视觉（使用 OpenAI 兼容格式）
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
        调用豆包 API（支持多模态）
        
        根据官方文档：
        - 端点: POST https://ark.cn-beijing.volces.com/api/v3/chat/completions
        - 认证: Authorization: Bearer {API_KEY}
        - 响应格式: 类似 OpenAI，包含 choices 数组
        """
        import httpx
        
        # 转换消息格式（使用 OpenAI 兼容格式）
        formatted_messages = [msg.to_openai_format() for msg in messages]
        
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


class ChatQwen(BaseLLM):
    """阿里云百炼 Qwen VL 接口 - 支持多模态"""
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        model: str = "qwen-vl-plus",
        base_url: Optional[str] = None
    ):
        """
        初始化通义千问模型
        
        阿里云百炼使用 OpenAI 兼容的 API 格式
        - API 端点: https://dashscope.aliyuncs.com/compatible-mode/v1
        - 认证方式: Authorization: Bearer {API_KEY}
        
        Args:
            api_key: API密钥，也可通过环境变量 QWEN_API_KEY 或 DASHSCOPE_API_KEY 设置
            model: 模型名称，默认为 qwen-vl-plus
                   可选: qwen-vl-plus, qwen-vl-max, qwen2.5-vl-72b-instruct
            base_url: API基础URL，默认为阿里云百炼端点
        """
        self.api_key = api_key or os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ValueError("需要提供 QWEN_API_KEY 或设置环境变量")
        super().__init__(self.api_key)
        self.model = model
        self.supports_vision = True  # Qwen VL 支持视觉
        self.base_url = base_url or os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        except ImportError:
            raise ImportError("请安装 openai: pip install openai")
    
    async def chat(self, messages: List[Message]) -> str:
        """调用 Qwen VL API（支持多模态）"""
        try:
            # 转换消息格式（使用 OpenAI 兼容格式）
            formatted_messages = []
            for msg in messages:
                formatted_msg = msg.to_openai_format()
                
                # Qwen VL 对图片格式有特殊要求，需要调整
                if isinstance(formatted_msg.get("content"), list):
                    new_content = []
                    for item in formatted_msg["content"]:
                        if item.get("type") == "image_url":
                            # Qwen VL 使用 image_url 格式
                            new_content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": item["image_url"]["url"]
                                }
                            })
                        else:
                            new_content.append(item)
                    formatted_msg["content"] = new_content
                
                formatted_messages.append(formatted_msg)
            
            logger.info(f"调用 Qwen VL API: {self.model}")
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=formatted_messages,
                temperature=0.7,
                max_tokens=4096,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Qwen VL API 调用失败: {e}")
            raise ValueError(f"Qwen VL API 调用失败: {str(e)}") from e


class ChatGemini(BaseLLM):
    """Google Gemini 接口 - 支持多模态"""
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        model: str = "gemini-2.0-flash",
    ):
        """
        初始化 Gemini 模型
        
        Args:
            api_key: API密钥，也可通过环境变量 GEMINI_API_KEY 设置
            model: 模型名称，默认为 gemini-2.0-flash
                   可选: gemini-1.5-pro, gemini-1.5-flash, gemini-2.0-flash
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("需要提供 GEMINI_API_KEY 或设置环境变量")
        super().__init__(self.api_key)
        self.model = model
        self.supports_vision = True  # Gemini 支持视觉
        
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.genai = genai
            self._model = genai.GenerativeModel(self.model)
        except ImportError:
            raise ImportError("请安装 google-generativeai: pip install google-generativeai")
    
    async def chat(self, messages: List[Message]) -> str:
        """调用 Gemini API（支持多模态）"""
        import asyncio
        
        try:
            # 转换消息格式为 Gemini 格式
            gemini_messages = []
            system_instruction = None
            
            for msg in messages:
                if msg.role == "system":
                    # Gemini 使用 system_instruction
                    if isinstance(msg.content, str):
                        system_instruction = msg.content
                    else:
                        system_instruction = msg.content[0].text if msg.content else ""
                    continue
                
                # 转换 role
                role = "user" if msg.role == "user" else "model"
                
                if isinstance(msg.content, str):
                    # 纯文本消息
                    gemini_messages.append({
                        "role": role,
                        "parts": [{"text": msg.content}]
                    })
                else:
                    # 多模态消息
                    parts = []
                    for item in msg.content:
                        if isinstance(item, TextContent):
                            parts.append({"text": item.text})
                        elif isinstance(item, ImageContent):
                            # Gemini 使用 inline_data 格式
                            parts.append({
                                "inline_data": {
                                    "mime_type": item.media_type,
                                    "data": item.image_data
                                }
                            })
                    gemini_messages.append({
                        "role": role,
                        "parts": parts
                    })
            
            # 如果有 system instruction，重新创建模型
            if system_instruction:
                model = self.genai.GenerativeModel(
                    self.model,
                    system_instruction=system_instruction
                )
            else:
                model = self._model
            
            # Gemini SDK 是同步的，需要在线程中运行
            def sync_generate():
                chat = model.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])
                
                # 获取最后一条消息的 parts
                if gemini_messages:
                    last_msg = gemini_messages[-1]
                    parts = last_msg.get("parts", [])
                    
                    # 转换 parts 为 Gemini 可接受的格式
                    gemini_parts = []
                    for part in parts:
                        if "text" in part:
                            gemini_parts.append(part["text"])
                        elif "inline_data" in part:
                            # 创建 PIL Image 或使用 base64
                            import base64
                            from io import BytesIO
                            try:
                                from PIL import Image
                                image_data = base64.b64decode(part["inline_data"]["data"])
                                image = Image.open(BytesIO(image_data))
                                gemini_parts.append(image)
                            except ImportError:
                                # 如果没有 PIL，使用字典格式
                                gemini_parts.append({
                                    "mime_type": part["inline_data"]["mime_type"],
                                    "data": part["inline_data"]["data"]
                                })
                    
                    response = chat.send_message(gemini_parts)
                else:
                    response = chat.send_message("Hello")
                
                return response.text
            
            # 在线程池中运行同步代码
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, sync_generate)
            return result
            
        except Exception as e:
            logger.error(f"Gemini API 调用失败: {e}")
            raise ValueError(f"Gemini API 调用失败: {str(e)}") from e