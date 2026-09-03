from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

SQLALCHEMY_DATABASE_URL = "sqlite:///./auctioniq.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    balance = Column(Float, default=1000.0)
    reputation_score = Column(Float, default=100.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # NEW PROFILE FIELDS
    bio = Column(String, nullable=True)
    avatar_color = Column(String, default="#6f42c1")
    total_bids = Column(Integer, default=0)
    total_won = Column(Integer, default=0)
    badges = Column(JSON, default=list)  # Store badge IDs
    
    bids = relationship("Bid", back_populates="user")
    auctions = relationship("Auction", back_populates="seller")
    notifications = relationship("Notification", back_populates="user")
    chat_messages = relationship("ChatMessage", back_populates="user")

class Auction(Base):
    __tablename__ = "auctions"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    starting_price = Column(Float)
    current_bid = Column(Float, default=0.0)
    end_time = Column(DateTime)
    is_active = Column(Boolean, default=True)
    seller_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    image_url = Column(String, nullable=True)
    category = Column(String, nullable=True)
    ai_risk_score = Column(Float, nullable=True)
    
    seller = relationship("User", back_populates="auctions")
    bids = relationship("Bid", back_populates="auction", order_by="Bid.timestamp.desc()")

class Bid(Base):
    __tablename__ = "bids"
    id = Column(Integer, primary_key=True, index=True)
    auction_id = Column(Integer, ForeignKey("auctions.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    is_flagged = Column(Boolean, default=False)
    is_automatic = Column(Boolean, default=False)
    
    auction = relationship("Auction", back_populates="bids")
    user = relationship("User", back_populates="bids")

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    message = Column(String)
    type = Column(String)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="notifications")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    message = Column(Text)
    response = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="chat_messages")



class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String)
    user_id = Column(Integer, nullable=True)
    auction_id = Column(Integer, nullable=True)
    event_metadata = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)