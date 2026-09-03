from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class UserLogin(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str

class AuctionCreate(BaseModel):
    title: str
    description: str
    starting_price: float
    duration_hours: int
    category: Optional[str] = None
    image_url: Optional[str] = None

class AuctionResponse(BaseModel):
    id: int
    title: str
    description: str
    starting_price: float
    current_bid: float
    end_time: datetime
    is_active: bool
    seller_id: int
    ai_prediction: Optional[float] = None
    ai_analysis: Optional[dict] = None
    
    class Config:
        from_attributes = True

class BidInput(BaseModel):
    amount: float
    user_id: int

class BidResponse(BaseModel):
    id: int
    amount: float
    user_id: int
    timestamp: datetime
    is_flagged: bool
    
    class Config:
        from_attributes = True

class AutoBotConfig(BaseModel):
    user_id: int
    auction_id: int
    max_bid: float
    strategy: str
    is_active: bool = True

class ChatRequest(BaseModel):
    message: str
    user_id: int

class NotificationResponse(BaseModel):
    id: int
    message: str
    type: str
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

# Add these to schemas.py

class UserProfileUpdate(BaseModel):
    username: Optional[str] = None
    bio: Optional[str] = None
    avatar_color: Optional[str] = None

class UserProfileResponse(BaseModel):
    id: int
    username: str
    bio: Optional[str] = None
    avatar_color: str
    balance: float
    reputation_score: float
    total_bids: int
    total_won: int
    badges: list
    created_at: datetime
    member_since: str
    
    class Config:
        from_attributes = True