from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
import logging

from .models import (
    Order, OrderRequest, OrderResponse, CancelOrderRequest,
    OrderBook, MarketData, Trade, User
)
from .matcher import MatchingEngine

logger = logging.getLogger(__name__)

# 创建全局撮合引擎实例
matching_engine = MatchingEngine()

# 创建路由
router = APIRouter()

# 模拟用户余额存储（实际应用中应该用数据库）
user_balances = {
    "user123": {"BTC": 10.0, "USDT": 100000.0},
    "user456": {"BTC": 5.0, "USDT": 50000.0},
    "user789": {"BTC": 2.0, "USDT": 20000.0}
}

async def get_user_balance(user_id: str) -> dict:
    """获取用户余额"""
    return user_balances.get(user_id, {"BTC": 0.0, "USDT": 0.0})

async def check_balance(user_id: str, symbol: str, side: str, quantity: float, price: float) -> bool:
    """检查用户余额是否足够"""
    balance = await get_user_balance(user_id)
    
    if side == "buy":
        # 买单需要检查计价货币余额
        base_symbol, quote_symbol = symbol.split("/")
        required_amount = quantity * price
        return balance.get(quote_symbol, 0) >= required_amount
    else:
        # 卖单需要检查基础货币余额
        base_symbol, quote_symbol = symbol.split("/")
        return balance.get(base_symbol, 0) >= quantity

async def update_balance_after_trade(trade: Trade):
    """交易后更新用户余额"""
    base_symbol, quote_symbol = trade.symbol.split("/")
    trade_value = trade.quantity * trade.price
    
    # 更新买方余额
    if trade.buyer_id in user_balances:
        user_balances[trade.buyer_id][base_symbol] += trade.quantity
        user_balances[trade.buyer_id][quote_symbol] -= trade_value
    
    # 更新卖方余额
    if trade.seller_id in user_balances:
        user_balances[trade.seller_id][base_symbol] -= trade.quantity
        user_balances[trade.seller_id][quote_symbol] += trade_value

@router.post("/orders", response_model=OrderResponse)
async def place_order(order_request: OrderRequest):
    """下单"""
    try:
        # 检查用户余额
        if not await check_balance(
            order_request.user_id,
            order_request.symbol,
            order_request.side.value,
            order_request.quantity,
            order_request.price or 0
        ):
            return OrderResponse(
                success=False,
                message="余额不足",
                order_id=None
            )
        
        # 创建订单
        order = Order(
            symbol=order_request.symbol,
            side=order_request.side,
            order_type=order_request.order_type,
            quantity=order_request.quantity,
            price=order_request.price,
            stop_price=order_request.stop_price,
            user_id=order_request.user_id,
            client_order_id=order_request.client_order_id
        )
        
        # 发送到撮合引擎
        trades = await matching_engine.process_order(order)
        
        # 更新用户余额
        for trade in trades:
            await update_balance_after_trade(trade)
        
        return OrderResponse(
            success=True,
            message="订单已提交",
            order_id=order.id,
            order=order
        )
        
    except Exception as e:
        logger.error(f"下单失败: {str(e)}")
        return OrderResponse(
            success=False,
            message=f"下单失败: {str(e)}",
            order_id=None
        )

@router.delete("/orders/{order_id}")
async def cancel_order(order_id: str, user_id: str):
    """取消订单"""
    try:
        success = await matching_engine.cancel_order(order_id, user_id)
        
        if success:
            return {"success": True, "message": "订单已取消"}
        else:
            return {"success": False, "message": "取消失败，订单不存在或无权限"}
            
    except Exception as e:
        logger.error(f"取消订单失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/orders/{order_id}", response_model=Order)
async def get_order(order_id: str):
    """获取订单详情"""
    order = matching_engine.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order

@router.get("/users/{user_id}/orders", response_model=List[Order])
async def get_user_orders(user_id: str):
    """获取用户的所有订单"""
    orders = matching_engine.get_user_orders(user_id)
    return orders

@router.get("/users/{user_id}/balance")
async def get_user_balance_api(user_id: str):
    """获取用户余额"""
    balance = await get_user_balance(user_id)
    return {
        "user_id": user_id,
        "balances": balance
    }

@router.get("/orderbook/{symbol}", response_model=OrderBook)
async def get_orderbook(symbol: str):
    """获取订单簿"""
    orderbook = matching_engine.get_orderbook(symbol)
    if not orderbook:
        raise HTTPException(status_code=404, detail="交易对不存在")
    return orderbook

@router.get("/market/{symbol}", response_model=MarketData)
async def get_market_data(symbol: str):
    """获取市场数据"""
    market_data = matching_engine.get_market_data(symbol)
    if not market_data:
        raise HTTPException(status_code=404, detail="市场数据不存在")
    return market_data

@router.get("/trades/{symbol}", response_model=List[Trade])
async def get_trades(symbol: str, limit: int = 100):
    """获取交易历史"""
    # 过滤指定交易对的交易记录
    trades = [
        trade for trade in matching_engine.trades
        if trade.symbol == symbol
    ]
    
    # 按时间倒序排列，返回最新的交易
    trades.sort(key=lambda x: x.timestamp, reverse=True)
    return trades[:limit]

@router.get("/trades")
async def get_all_trades(limit: int = 100):
    """获取所有交易历史"""
    trades = sorted(matching_engine.trades, key=lambda x: x.timestamp, reverse=True)
    return trades[:limit]

@router.get("/stats")
async def get_system_stats():
    """获取系统统计信息"""
    return {
        "total_orders": len(matching_engine.active_orders),
        "total_trades": len(matching_engine.trades),
        "active_symbols": list(matching_engine.order_books.keys()),
        "system_status": "running"
    }

# 测试数据初始化
@router.post("/test/init")
async def init_test_data():
    """初始化测试数据"""
    # 添加一些测试订单
    test_orders = [
        OrderRequest(
            symbol="BTC/USDT",
            side="sell",
            order_type="limit",
            quantity=1.0,
            price=49000,
            user_id="user456"
        ),
        OrderRequest(
            symbol="BTC/USDT",
            side="sell",
            order_type="limit",
            quantity=0.5,
            price=49500,
            user_id="user789"
        ),
        OrderRequest(
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=0.8,
            price=48500,
            user_id="user123"
        )
    ]
    
    created_orders = []
    for order_req in test_orders:
        order = Order(
            symbol=order_req.symbol,
            side=order_req.side,
            order_type=order_req.order_type,
            quantity=order_req.quantity,
            price=order_req.price,
            user_id=order_req.user_id
        )
        
        await matching_engine.process_order(order)
        created_orders.append(order.id)
    
    return {
        "message": "测试数据已初始化",
        "created_orders": created_orders
    } 