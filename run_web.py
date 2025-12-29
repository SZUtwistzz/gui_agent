"""启动 Web GUI 服务器"""

import uvicorn
from web_server import app

if __name__ == "__main__":
    print("🚀 启动轻量级 Web GUI Agent...")
    print("📱 打开浏览器访问: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

