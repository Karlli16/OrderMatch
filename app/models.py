from pydantic import BaseModel,Field




class OrderType(str,Enum):
    Limit="limit"
    Market="market"
    Stop="stop"

class OrderSide(str,Enum):
    Buy="buy"
    Sell="sell"

class OrderStatus(str,Enum):
    Pending="pending"
    Partial="partial"
    Filled="filled"
    Cancelled="cancelled"
    Rejected="rejected"

class UserStatus(str,Enum):
    Active="active"
    Banned="banned"
    Pending="pending"




class Order(BaseModel):
    id: str=Field(default_factory=lambda: str(uuid.uuid4()))
    symbol:str=Field(...)
    side:OrderSide=Field(...)
    order_type:OrderType=Field(...)
    quantity:float=Field(...,gt=0)
    price:Optional[float]=Field(None,gt=0)
    stop_price:Optional[float]=Field(None,gt=0)


    status:OrderStatus=Field(default=OrderStatus.Pending)
    filled_quantity:float=Field(default=0)
    average_price:Optional[float]=Field(None)

    created_at:datetime=Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at:datetime=Field(default_factory=lambda: datetime.now(timezone.utc))

    user_id:str=Field(...)
    client_order_id:str=Field(...)


class User(BaseModel):
    id:str=Field(default_factory=lambda: str(uuid.uuid4()))
    username:str=Field(...)
    email:str=Field(...)

    status:UserStatus=Field(default=UserStatus.Pending)

    is_verified:bool=Field(default=False)

    created_at:datetime=Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at:datetime=Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login:datetime=Field(default_factory=lambda: datetime.now(timezone.utc))

    two_factor_enabled:bool=Field(default=False)
    api_enabled:bool=Field(default=False)

class UserBalance(BaseModel):
    user_id:str=Field(...)
    symbol:str=Field(...)

    available_balance:float=Field(default=0,ge=0)
    frozen_balance:float=Field(default=0,ge=0)

    @property
    def total(self)->float:
        return self.available_balance+self.frozen_balance
    
    updated_at:datetime=Field(default_factory=lambda: datetime.now(timezone.utc))


class UserTradingLimits(BaseModel):
    user_id:str=Field(...)
    single_order_limit:float=Field(default=10000.0,ge=0)

    daily_limit:float=Field(default=100000.0,ge=0)
    monthly_limit:float=Field(default=300000.0,ge=0)

    daily_withdrawal_limit:float=Field(default=5000.0,ge=0)
    monthly_withdrawal_limit:float=Field(default=20000.0,ge=0)

    max_open_orders:int=Field(default=10,ge=0)
    api_rate_limit:int=Field(default=1000,ge=0)

class UserProfile(BaseModel):
    """用户详细信息"""
    user_id: str = Field(..., description="用户ID")
    
    # 个人信息
    first_name: Optional[str] = Field(None, description="名")
    last_name: Optional[str] = Field(None, description="姓")
    date_of_birth: Optional[datetime] = Field(None, description="出生日期")
    country: Optional[str] = Field(None, description="国家")
    city: Optional[str] = Field(None, description="城市")
    
    # 偏好设置
    preferred_language: str = Field(default="zh-CN", description="首选语言")
    timezone: str = Field(default="Asia/Shanghai", description="时区")
    notification_email: bool = Field(default=True, description="邮件通知")
    notification_sms: bool = Field(default=False, description="短信通知")
    
    # 交易偏好
    default_trading_pair: str = Field(default="BTC/USDT", description="默认交易对")
    risk_level: str = Field(default="medium", description="风险等级")

class UserSession(BaseModel):
    """用户会话"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(..., description="用户ID")
    token: str = Field(..., description="会话令牌")
    
    # 会话信息
    ip_address: str = Field(..., description="IP地址")
    user_agent: str = Field(..., description="用户代理")
    device_type: str = Field(default="web", description="设备类型")
    
    # 时间信息
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(..., description="过期时间")
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    
    # 状态
    is_active: bool = Field(default=True, description="是否活跃")

class UserApiKey(BaseModel):
    """用户API密钥"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(..., description="用户ID")
    name: str = Field(..., description="API密钥名称")
    
    # 密钥信息
    api_key: str = Field(..., description="API密钥")
    secret_key: str = Field(..., description="密钥(加密存储)")
    
    # 权限设置
    can_trade: bool = Field(default=False, description="是否可以交易")
    can_withdraw: bool = Field(default=False, description="是否可以提现")
    can_read: bool = Field(default=True, description="是否可以读取")
    
    # IP白名单
    ip_whitelist: List[str] = Field(default_factory=list, description="IP白名单")
    
    # 时间信息
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    last_used: Optional[datetime] = Field(None, description="最后使用时间")
    
    # 状态
    is_active: bool = Field(default=True, description="是否启用")

# 请求和响应模型
class UserRegistrationRequest(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(...)
    password: str = Field(..., min_length=8)
    phone: Optional[str] = None
    referral_code: Optional[str] = None

class UserLoginRequest(BaseModel):
    """用户登录请求"""
    username: str = Field(...)
    password: str = Field(...)
    two_factor_code: Optional[str] = None

class UserResponse(BaseModel):
    """用户响应"""
    success: bool
    message: str
    user: Optional[User] = None
    token: Optional[str] = None

class BalanceResponse(BaseModel):
    """余额响应"""
    user_id: str
    balances: Dict[str, UserBalance]
    total_value_usdt: float = Field(description="总价值(USDT)")

# class OrderBook(BaseModel):

# class OrderBook(BaseModel):