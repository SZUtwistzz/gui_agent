"""轻量级 Web GUI Agent"""

try:
    from .agent import Agent
    from .browser import Browser
    from .llm import ChatOpenAI, ChatAnthropic, ChatDoubao
except ImportError:
    from agent import Agent
    from browser import Browser
    from llm import ChatOpenAI, ChatAnthropic, ChatDoubao

__version__ = "0.1.0"
__all__ = ["Agent", "Browser", "ChatOpenAI", "ChatAnthropic", "ChatDoubao"]

