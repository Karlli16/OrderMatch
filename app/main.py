from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
import logging
from typing import Dict, List
import json

from .routes import router
from .matcher import matching_engine

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局变量存储WebSocket连接
active_connections: List[WebSocket] = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时的初始化
    logger.info("🚀 OrderMatch 系统启动中...")
    logger.info("📊 撮合引擎已准备就绪")
    yield
    # 关闭时的清理
    logger.info("🛑 OrderMatch 系统关闭中...")

app = FastAPI(
    title="OrderMatch 订单撮合系统",
    description="高性能订单撮合引擎，支持限价单、市价单，实时撮合",
    version="1.0.0",
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 包含API路由
app.include_router(router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {
        "message": "OrderMatch 订单撮合系统",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "api_prefix": "/api/v1"
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "ordermatch",
        "engine_status": "running",
        "active_orders": len(matching_engine.active_orders),
        "total_trades": len(matching_engine.trades)
    }

# WebSocket连接管理
@app.websocket("/ws/orders")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    logger.info(f"WebSocket连接已建立，当前连接数: {len(active_connections)}")
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                
                # 处理不同类型的WebSocket消息
                if message.get("type") == "subscribe":
                    # 订阅市场数据
                    symbol = message.get("symbol", "BTC/USDT")
                    await websocket.send_text(json.dumps({
                        "type": "subscribed",
                        "symbol": symbol,
                        "message": f"已订阅 {symbol} 市场数据"
                    }))
                
                elif message.get("type") == "place_order":
                    # 通过WebSocket下单
                    await websocket.send_text(json.dumps({
                        "type": "info",
                        "message": "WebSocket下单功能开发中..."
                    }))
                
                else:
                    # 回显消息
                    await websocket.send_text(json.dumps({
                        "type": "echo",
                        "received": message
                    }))
                    
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "消息格式错误，请发送JSON格式"
                }))
                
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logger.info(f"WebSocket连接已断开，当前连接数: {len(active_connections)}")

# 广播消息到所有连接的客户端
async def broadcast_message(message: dict):
    """广播消息到所有WebSocket连接"""
    if active_connections:
        message_str = json.dumps(message)
        disconnected = []
        
        for connection in active_connections:
            try:
                await connection.send_text(message_str)
            except:
                disconnected.append(connection)
        
        # 清理断开的连接
        for connection in disconnected:
            active_connections.remove(connection)

# 广播交易信息（可以在撮合引擎中调用）
async def broadcast_trade(trade):
    """广播交易信息"""
    await broadcast_message({
        "type": "trade",
        "data": {
            "symbol": trade.symbol,
            "price": trade.price,
            "quantity": trade.quantity,
            "timestamp": trade.timestamp.isoformat()
        }
    })

# 广播订单簿更新
async def broadcast_orderbook_update(symbol: str):
    """广播订单簿更新"""
    orderbook = matching_engine.get_orderbook(symbol)
    if orderbook:
        await broadcast_message({
            "type": "orderbook",
            "symbol": symbol,
            "data": {
                "bids": orderbook.bids[:10],  # 只发送前10档
                "asks": orderbook.asks[:10],
                "last_updated": orderbook.last_updated.isoformat()
            }
        })

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)