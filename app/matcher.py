from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import asyncio
import logging
from datetime import datetime

from .models import (
    Order, OrderSide, OrderStatus, OrderType, 
    Trade, OrderBook, MarketData
)

logger = logging.getLogger(__name__)

class MatchingEngine:
    """订单撮合引擎"""
    
    def __init__(self):
        # 每个交易对的订单簿
        self.order_books: Dict[str, OrderBook] = {}
        
        # 活跃订单存储 {order_id: order}
        self.active_orders: Dict[str, Order] = {}
        
        # 按交易对分组的订单 {symbol: {buy_orders: [], sell_orders: []}}
        self.orders_by_symbol: Dict[str, Dict[str, List[Order]]] = defaultdict(
            lambda: {"buy_orders": [], "sell_orders": []}
        )
        
        # 成交记录
        self.trades: List[Trade] = []
        
        # 市场数据
        self.market_data: Dict[str, MarketData] = {}
        
        logger.info("撮合引擎已启动")
    
    async def process_order(self, order: Order) -> List[Trade]:
        """处理新订单"""
        logger.info(f"处理订单: {order.id}, {order.symbol}, {order.side}, {order.quantity}@{order.price}")
        
        # 验证订单
        if not self._validate_order(order):
            order.status = OrderStatus.REJECTED
            return []
        
        # 初始化订单簿（如果不存在）
        if order.symbol not in self.order_books:
            self.order_books[order.symbol] = OrderBook(symbol=order.symbol)
        
        # 存储订单
        self.active_orders[order.id] = order
        
        # 尝试撮合
        trades = await self._match_order(order)
        
        # 如果订单未完全成交，加入订单簿
        if order.status != OrderStatus.FILLED:
            self._add_to_orderbook(order)
        
        # 更新市场数据
        if trades:
            await self._update_market_data(order.symbol, trades[-1])
        
        return trades
    
    def _validate_order(self, order: Order) -> bool:
        """验证订单有效性"""
        if order.quantity <= 0:
            logger.warning(f"订单数量无效: {order.quantity}")
            return False
        
        if order.order_type == OrderType.LIMIT and (not order.price or order.price <= 0):
            logger.warning(f"限价单价格无效: {order.price}")
            return False
        
        return True
    
    async def _match_order(self, new_order: Order) -> List[Trade]:
        """撮合订单"""
        trades = []
        orderbook = self.order_books[new_order.symbol]
        
        if new_order.side == OrderSide.BUY:
            # 买单与卖单撮合
            trades = await self._match_buy_order(new_order, orderbook)
        else:
            # 卖单与买单撮合
            trades = await self._match_sell_order(new_order, orderbook)
        
        return trades
    
    async def _match_buy_order(self, buy_order: Order, orderbook: OrderBook) -> List[Trade]:
        """撮合买单"""
        trades = []
        symbol_orders = self.orders_by_symbol[buy_order.symbol]
        
        # 按价格排序的卖单（价格从低到高）
        sell_orders = sorted(
            [o for o in symbol_orders["sell_orders"] if o.status == OrderStatus.PENDING],
            key=lambda x: (x.price or float('inf'), x.created_at)
        )
        
        for sell_order in sell_orders:
            if buy_order.quantity - buy_order.filled_quantity <= 0:
                break
            
            # 检查价格匹配
            if not self._price_matches(buy_order, sell_order):
                continue
            
            # 执行交易
            trade = await self._execute_trade(buy_order, sell_order)
            if trade:
                trades.append(trade)
                self.trades.append(trade)
        
        return trades
    
    async def _match_sell_order(self, sell_order: Order, orderbook: OrderBook) -> List[Trade]:
        """撮合卖单"""
        trades = []
        symbol_orders = self.orders_by_symbol[sell_order.symbol]
        
        # 按价格排序的买单（价格从高到低）
        buy_orders = sorted(
            [o for o in symbol_orders["buy_orders"] if o.status == OrderStatus.PENDING],
            key=lambda x: (-(x.price or 0), x.created_at)
        )
        
        for buy_order in buy_orders:
            if sell_order.quantity - sell_order.filled_quantity <= 0:
                break
            
            # 检查价格匹配
            if not self._price_matches(buy_order, sell_order):
                continue
            
            # 执行交易
            trade = await self._execute_trade(buy_order, sell_order)
            if trade:
                trades.append(trade)
                self.trades.append(trade)
        
        return trades
    
    def _price_matches(self, buy_order: Order, sell_order: Order) -> bool:
        """检查买卖单价格是否匹配"""
        # 市价单总是匹配
        if buy_order.order_type == OrderType.MARKET or sell_order.order_type == OrderType.MARKET:
            return True
        
        # 限价单：买价 >= 卖价
        if buy_order.price and sell_order.price:
            return buy_order.price >= sell_order.price
        
        return False
    
    async def _execute_trade(self, buy_order: Order, sell_order: Order) -> Optional[Trade]:
        """执行交易"""
        # 计算成交数量
        buy_remaining = buy_order.quantity - buy_order.filled_quantity
        sell_remaining = sell_order.quantity - sell_order.filled_quantity
        trade_quantity = min(buy_remaining, sell_remaining)
        
        if trade_quantity <= 0:
            return None
        
        # 确定成交价格（价格优先原则）
        if buy_order.order_type == OrderType.MARKET:
            trade_price = sell_order.price
        elif sell_order.order_type == OrderType.MARKET:
            trade_price = buy_order.price
        else:
            # 时间优先：先下单的价格优先
            if buy_order.created_at < sell_order.created_at:
                trade_price = buy_order.price
            else:
                trade_price = sell_order.price
        
        # 创建交易记录
        trade = Trade(
            symbol=buy_order.symbol,
            buy_order_id=buy_order.id,
            sell_order_id=sell_order.id,
            buyer_id=buy_order.user_id,
            seller_id=sell_order.user_id,
            quantity=trade_quantity,
            price=trade_price
        )
        
        # 更新订单状态
        await self._update_order_after_trade(buy_order, trade_quantity, trade_price)
        await self._update_order_after_trade(sell_order, trade_quantity, trade_price)
        
        logger.info(f"成交: {trade.quantity} {trade.symbol} @ {trade.price}")
        return trade
    
    async def _update_order_after_trade(self, order: Order, trade_quantity: float, trade_price: float):
        """交易后更新订单状态"""
        # 更新已成交数量
        order.filled_quantity += trade_quantity
        
        # 更新平均成交价格
        if order.average_price is None:
            order.average_price = trade_price
        else:
            total_value = (order.filled_quantity - trade_quantity) * order.average_price
            total_value += trade_quantity * trade_price
            order.average_price = total_value / order.filled_quantity
        
        # 更新订单状态
        if order.filled_quantity >= order.quantity:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIAL
        
        order.updated_at = datetime.utcnow()
    
    def _add_to_orderbook(self, order: Order):
        """将订单加入订单簿"""
        symbol_orders = self.orders_by_symbol[order.symbol]
        
        if order.side == OrderSide.BUY:
            symbol_orders["buy_orders"].append(order)
        else:
            symbol_orders["sell_orders"].append(order)
        
        # 更新订单簿快照
        self._update_orderbook_snapshot(order.symbol)
    
    def _update_orderbook_snapshot(self, symbol: str):
        """更新订单簿快照"""
        symbol_orders = self.orders_by_symbol[symbol]
        orderbook = self.order_books[symbol]
        
        # 聚合买单（按价格分组）
        buy_levels = defaultdict(float)
        for order in symbol_orders["buy_orders"]:
            if order.status == OrderStatus.PENDING and order.price:
                remaining = order.quantity - order.filled_quantity
                buy_levels[order.price] += remaining
        
        # 聚合卖单（按价格分组）
        sell_levels = defaultdict(float)
        for order in symbol_orders["sell_orders"]:
            if order.status == OrderStatus.PENDING and order.price:
                remaining = order.quantity - order.filled_quantity
                sell_levels[order.price] += remaining
        
        # 更新订单簿
        orderbook.bids = [
            {"price": price, "quantity": quantity}
            for price, quantity in sorted(buy_levels.items(), reverse=True)
        ]
        
        orderbook.asks = [
            {"price": price, "quantity": quantity}
            for price, quantity in sorted(sell_levels.items())
        ]
        
        orderbook.last_updated = datetime.utcnow()
    
    async def _update_market_data(self, symbol: str, trade: Trade):
        """更新市场数据"""
        if symbol not in self.market_data:
            self.market_data[symbol] = MarketData(
                symbol=symbol,
                last_price=trade.price,
                bid=0,
                ask=0,
                volume_24h=0,
                change_24h=0
            )
        
        market_data = self.market_data[symbol]
        old_price = market_data.last_price
        
        # 更新最新价格
        market_data.last_price = trade.price
        
        # 更新买一卖一价格
        orderbook = self.order_books[symbol]
        if orderbook.bids:
            market_data.bid = orderbook.bids[0]["price"]
        if orderbook.asks:
            market_data.ask = orderbook.asks[0]["price"]
        
        # 计算24小时涨跌幅
        if old_price > 0:
            market_data.change_24h = ((trade.price - old_price) / old_price) * 100
        
        market_data.timestamp = datetime.utcnow()
    
    async def cancel_order(self, order_id: str, user_id: str) -> bool:
        """取消订单"""
        if order_id not in self.active_orders:
            return False
        
        order = self.active_orders[order_id]
        
        # 检查权限
        if order.user_id != user_id:
            return False
        
        # 检查订单状态
        if order.status not in [OrderStatus.PENDING, OrderStatus.PARTIAL]:
            return False
        
        # 更新订单状态
        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.utcnow()
        
        # 从订单簿中移除
        self._remove_from_orderbook(order)
        
        logger.info(f"订单已取消: {order_id}")
        return True
    
    def _remove_from_orderbook(self, order: Order):
        """从订单簿中移除订单"""
        symbol_orders = self.orders_by_symbol[order.symbol]
        
        if order.side == OrderSide.BUY:
            symbol_orders["buy_orders"] = [
                o for o in symbol_orders["buy_orders"] if o.id != order.id
            ]
        else:
            symbol_orders["sell_orders"] = [
                o for o in symbol_orders["sell_orders"] if o.id != order.id
            ]
        
        # 更新订单簿快照
        self._update_orderbook_snapshot(order.symbol)
    
    def get_orderbook(self, symbol: str) -> Optional[OrderBook]:
        """获取订单簿"""
        return self.order_books.get(symbol)
    
    def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """获取市场数据"""
        return self.market_data.get(symbol)
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单"""
        return self.active_orders.get(order_id)
    
    def get_user_orders(self, user_id: str) -> List[Order]:
        """获取用户的所有订单"""
        return [
            order for order in self.active_orders.values()
            if order.user_id == user_id
        ] 