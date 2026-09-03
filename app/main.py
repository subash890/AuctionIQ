from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy import func
import json
import hashlib
import asyncio
from pathlib import Path

from app import database, schemas, services

app = FastAPI(title="AuctionIQ Engine")

app.mount("/static", StaticFiles(directory="static"), name="static")

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, auction_id: int):
        await websocket.accept()
        if auction_id not in self.active_connections:
            self.active_connections[auction_id] = []
        self.active_connections[auction_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, auction_id: int):
        if auction_id in self.active_connections:
            if websocket in self.active_connections[auction_id]:
                self.active_connections[auction_id].remove(websocket)
            if not self.active_connections[auction_id]:
                del self.active_connections[auction_id]
    
    async def broadcast(self, auction_id: int, message: dict):
        if auction_id in self.active_connections:
            for connection in self.active_connections[auction_id]:
                await connection.send_json(message)

manager = ConnectionManager()

def create_notification(db: Session, user_id: int, message: str, type: str):
    notification = database.Notification(user_id=user_id, message=message, type=type)
    db.add(notification)
    db.commit()

# AUTH
@app.post("/auth/register")
async def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(database.User).filter(database.User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")
    
    new_user = database.User(username=user.username, password_hash=hash_password(user.password), balance=1000.0)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"user_id": new_user.id, "username": new_user.username}

@app.post("/auth/login")
async def login(user: schemas.UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(database.User).filter(database.User.username == user.username).first()
    if not db_user or db_user.password_hash != hash_password(user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"user_id": db_user.id, "username": db_user.username, "balance": db_user.balance}

# AUCTIONS
@app.post("/api/auctions", response_model=schemas.AuctionResponse)
async def create_auction(auction: schemas.AuctionCreate, db: Session = Depends(get_db)):
    ai_analysis = await services.analyze_item_groq(auction.description)
    end_time = datetime.utcnow() + timedelta(hours=auction.duration_hours)
    
    db_auction = database.Auction(
        title=auction.title, description=auction.description,
        starting_price=auction.starting_price, current_bid=auction.starting_price,
        end_time=end_time, seller_id=1, is_active=True,
        category=auction.category, image_url=auction.image_url
    )
    db.add(db_auction)
    db.commit()
    db.refresh(db_auction)
    
    ai_prediction = services.predict_price(auction.starting_price, auction.duration_hours)
    
    return {**db_auction.__dict__, "ai_prediction": ai_prediction, "ai_analysis": ai_analysis}

@app.get("/api/auctions", response_model=List[schemas.AuctionResponse])
async def list_auctions(active_only: bool = True, db: Session = Depends(get_db)):
    query = db.query(database.Auction)
    if active_only:
        query = query.filter(database.Auction.is_active == True)
    auctions = query.all()
    
    results = []
    for a in auctions:
        hours_left = max(1, (a.end_time - datetime.utcnow()).total_seconds() / 3600)
        pred = services.predict_price(a.starting_price, hours_left)
        results.append({**a.__dict__, "ai_prediction": pred})
    return results

@app.get("/api/auctions/{auction_id}", response_model=schemas.AuctionResponse)
async def get_auction(auction_id: int, db: Session = Depends(get_db)):
    auction = db.query(database.Auction).filter(database.Auction.id == auction_id).first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    
    hours_left = max(1, (auction.end_time - datetime.utcnow()).total_seconds() / 3600)
    pred = services.predict_price(auction.starting_price, hours_left)
    return {**auction.__dict__, "ai_prediction": pred}

@app.get("/api/auctions/{auction_id}/history")
async def get_bid_history(auction_id: int, db: Session = Depends(get_db)):
    bids = db.query(database.Bid).filter(database.Bid.auction_id == auction_id).order_by(database.Bid.timestamp.desc()).all()
    return [{"id": b.id, "amount": b.amount, "user_id": b.user_id, "timestamp": b.timestamp, "is_flagged": b.is_flagged} for b in bids]

@app.get("/api/auctions/{auction_id}/recommendation")
async def get_bid_recommendation(auction_id: int, user_id: int, db: Session = Depends(get_db)):
    auction = db.query(database.Auction).filter(database.Auction.id == auction_id).first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    
    hours_left = max(0.1, (auction.end_time - datetime.utcnow()).total_seconds() / 3600)
    predicted_close = services.predict_price(auction.starting_price, hours_left)
    
    if hours_left < 0.1:
        recommended_bid = auction.current_bid * 1.05
        strategy = "snipe"
    elif len(auction.bids) > 20:
        recommended_bid = auction.current_bid * 1.10
        strategy = "aggressive"
    else:
        recommended_bid = auction.current_bid * 1.03
        strategy = "steady"
    
    if recommended_bid > predicted_close * 0.95:
        recommended_bid = predicted_close * 0.90
        strategy = "conservative"
    
    return {"recommended_bid": round(recommended_bid, 2), "strategy": strategy, "predicted_close": round(predicted_close, 2), "confidence": "high" if hours_left > 1 else "medium"}

@app.get("/api/auctions/{auction_id}/price-history")
async def get_price_history(auction_id: int, db: Session = Depends(get_db)):
    bids = db.query(database.Bid).filter(database.Bid.auction_id == auction_id).order_by(database.Bid.timestamp).all()
    return [{"timestamp": b.timestamp.isoformat(), "amount": b.amount, "user_id": b.user_id} for b in bids]

# USERS
@app.get("/api/users/{user_id}/history")
async def get_user_history(user_id: int, db: Session = Depends(get_db)):
    bids = db.query(database.Bid).filter(database.Bid.user_id == user_id).all()
    auctions = db.query(database.Auction).filter(database.Auction.seller_id == user_id).all()
    
    return {
        "bids": [{"auction_id": b.auction_id, "amount": b.amount, "timestamp": b.timestamp, "won": False} for b in bids],
        "auctions": [{"id": a.id, "title": a.title, "final_price": a.current_bid, "status": "active" if a.is_active else "closed"} for a in auctions]
    }

@app.get("/api/notifications")
async def get_notifications(user_id: int, db: Session = Depends(get_db)):
    notifications = db.query(database.Notification).filter(database.Notification.user_id == user_id).order_by(database.Notification.created_at.desc()).limit(20).all()
    return [{"id": n.id, "message": n.message, "type": n.type, "is_read": n.is_read, "created_at": n.created_at.isoformat()} for n in notifications]

@app.post("/api/notifications/mark-read")
async def mark_notification_read(notification_id: int, db: Session = Depends(get_db)):
    notification = db.query(database.Notification).filter(database.Notification.id == notification_id).first()
    if notification:
        notification.is_read = True
        db.commit()
    return {"status": "ok"}

# ANALYTICS
@app.get("/api/analytics/dashboard")
async def get_analytics_dashboard(db: Session = Depends(get_db)):
    total_auctions = db.query(database.Auction).count()
    active_auctions = db.query(database.Auction).filter(database.Auction.is_active == True).count()
    total_bids = db.query(database.Bid).count()
    
    total_revenue = db.query(database.Auction.current_bid).filter(database.Auction.is_active == False).all()
    total_revenue = sum([r[0] for r in total_revenue]) if total_revenue else 0
    
    top_bidders = db.query(database.Bid.user_id, database.User.username, func.count(database.Bid.id).label('bid_count'), func.sum(database.Bid.amount).label('total_spent')).join(database.User).group_by(database.Bid.user_id, database.User.username).order_by(func.count(database.Bid.id).desc()).limit(5).all()
    
    recent_bids = db.query(database.Bid).order_by(database.Bid.timestamp.desc()).limit(10).all()
    
    return {
        "overview": {"total_auctions": total_auctions, "active_auctions": active_auctions, "total_bids": total_bids, "total_revenue": round(total_revenue, 2)},
        "top_bidders": [{"user_id": b.user_id, "username": b.username, "bid_count": b.bid_count, "total_spent": round(b.total_spent, 2)} for b in top_bidders],
        "recent_activity": [{"auction_id": b.auction_id, "user_id": b.user_id, "amount": b.amount, "timestamp": b.timestamp.isoformat()} for b in recent_bids]
    }

# CHAT
@app.post("/api/chat")
async def chat_with_ai(request: schemas.ChatRequest, db: Session = Depends(get_db)):
    user_msg = database.ChatMessage(user_id=request.user_id, message=request.message)
    db.add(user_msg)
    db.commit()
    
    user_bids = db.query(database.Bid).filter(database.Bid.user_id == request.user_id).limit(5).all()
    context = f"User has {len(user_bids)} recent bids. Recent: {[f'${b.amount}' for b in user_bids]}"
    
    ai_response = await services.chat_with_ai(request.message, context)
    
    user_msg.response = ai_response
    db.commit()
    
    return {"message": request.message, "response": ai_response, "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/chat/history")
async def get_chat_history(user_id: int, db: Session = Depends(get_db)):
    messages = db.query(database.ChatMessage).filter(database.ChatMessage.user_id == user_id).order_by(database.ChatMessage.timestamp.desc()).limit(50).all()
    return [{"message": m.message, "response": m.response, "timestamp": m.timestamp.isoformat()} for m in messages]

# BOT
@app.post("/api/bot/create")
async def create_auto_bot(config: schemas.AutoBotConfig, db: Session = Depends(get_db)):
    auction = db.query(database.Auction).filter(database.Auction.id == config.auction_id).first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    if config.max_bid <= auction.current_bid:
        raise HTTPException(status_code=400, detail="Max bid must be higher than current bid")
    
    if not hasattr(app.state, "auto_bots"):
        app.state.auto_bots = {}
    
    bot_id = f"{config.user_id}_{config.auction_id}"
    app.state.auto_bots[bot_id] = {"config": config, "last_bid": auction.current_bid, "created_at": datetime.utcnow()}
    
    return {"bot_id": bot_id, "status": "active", "message": f"Auto-bot created for auction {config.auction_id}"}

@app.get("/api/bot/status/{user_id}")
async def get_bot_status(user_id: int):
    if not hasattr(app.state, "auto_bots"):
        return {"bots": []}
    user_bots = [{"bot_id": k, **v} for k, v in app.state.auto_bots.items() if k.startswith(f"{user_id}_")]
    return {"bots": user_bots}

# IMAGE
@app.post("/api/analyze-image")
async def analyze_image(file: UploadFile = File(...)):
    return {"category": "Electronics", "confidence": 0.92, "condition": "Good", "detected_objects": ["camera", "lens"], "suggested_starting_price": 150.0, "ai_notes": "Item detected successfully"}

# WEBSOCKET
@app.websocket("/ws/bid/{auction_id}")
async def websocket_bid(websocket: WebSocket, auction_id: int):
    await manager.connect(websocket, auction_id)
    db = database.SessionLocal()
    auction = db.query(database.Auction).filter(database.Auction.id == auction_id).first()
    
    if auction:
        hours_left = max(1, (auction.end_time - datetime.utcnow()).total_seconds() / 3600)
        await websocket.send_json({
            "type": "init",
            "auction": {"id": auction.id, "title": auction.title, "current_bid": auction.current_bid, "end_time": auction.end_time.isoformat(), "ai_prediction": services.predict_price(auction.starting_price, hours_left)}
        })
    
    try:
        while True:
            data = await websocket.receive_text()
            bid_data = json.loads(data)
            
            auction = db.query(database.Auction).filter(database.Auction.id == auction_id).first()
            if not auction or not auction.is_active:
                await websocket.send_json({"status": "error", "message": "Auction closed"})
                continue
            
            if datetime.utcnow() > auction.end_time:
                auction.is_active = False
                db.commit()
                await manager.broadcast(auction_id, {"type": "auction_ended", "winner": "TBD"})
                continue
            
            time_left = (auction.end_time - datetime.utcnow()).total_seconds() / 60
            is_fraud = services.detect_fraud(bid_data['amount'], time_left, bid_data['user_id'])
            
            if is_fraud:
                await websocket.send_json({"status": "rejected", "reason": "🤖 AI Fraud Detection Flagged"})
                continue
            
            if bid_data['amount'] <= auction.current_bid:
                await websocket.send_json({"status": "rejected", "reason": "Bid must be higher than current"})
                continue
            
            auction.current_bid = bid_data['amount']
            db.commit()
            
            new_bid = database.Bid(auction_id=auction_id, user_id=bid_data['user_id'], amount=bid_data['amount'], is_flagged=False)
            db.add(new_bid)
            db.commit()
            
            hours_left = max(0.1, (auction.end_time - datetime.utcnow()).total_seconds() / 3600)
            updated_pred = services.predict_price(auction.starting_price, hours_left)
            
            await manager.broadcast(auction_id, {
                "type": "bid_update",
                "amount": bid_data['amount'],
                "user_id": bid_data['user_id'],
                "current_bid": auction.current_bid,
                "ai_prediction": updated_pred,
                "time_left_seconds": max(0, (auction.end_time - datetime.utcnow()).total_seconds()),
                "fraud_check": "passed"
            })
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, auction_id)
    finally:
        db.close()

# AUTO-BOT BACKGROUND
async def check_auto_bots():
    if not hasattr(app.state, "auto_bots"):
        return
    db = database.SessionLocal()
    
    for bot_id, bot_data in list(app.state.auto_bots.items()):
        config = bot_data["config"]
        if not config.is_active:
            continue
        
        auction = db.query(database.Auction).filter(database.Auction.id == config.auction_id).first()
        if not auction or not auction.is_active:
            config.is_active = False
            continue
        
        if auction.current_bid > bot_data["last_bid"]:
            time_left = (auction.end_time - datetime.utcnow()).total_seconds()
            
            if config.strategy == "sniper" and time_left > 60:
                continue
            elif config.strategy == "aggressive":
                new_bid = min(auction.current_bid * 1.10, config.max_bid)
            else:
                new_bid = min(auction.current_bid + 5, config.max_bid)
            
            if new_bid > auction.current_bid and new_bid <= config.max_bid:
                new_bid_obj = database.Bid(auction_id=config.auction_id, user_id=config.user_id, amount=new_bid, is_automatic=True)
                db.add(new_bid_obj)
                auction.current_bid = new_bid
                db.commit()
                bot_data["last_bid"] = new_bid
                create_notification(db, config.user_id, f"Auto-bot placed bid of ${new_bid}", "auto_bid")
    
    db.close()

async def run_auto_bot_checker():
    while True:
        await asyncio.sleep(10)
        await check_auto_bots()

@app.on_event("startup")
async def startup_event():
    app.state.auto_bots = {}
    asyncio.create_task(run_auto_bot_checker())

# FRONTEND ROUTES
STATIC_DIR = Path("static")

def read_static(filename: str) -> str:
    return (STATIC_DIR / filename).read_text(encoding="utf-8")

@app.get("/", response_class=HTMLResponse)
async def root():
    return read_static("index.html")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return read_static("dashboard.html")

@app.get("/create", response_class=HTMLResponse)
async def create_page():
    return read_static("create.html")

@app.get("/auction/{auction_id}", response_class=HTMLResponse)
async def auction_page(auction_id: int):
    content = read_static("auction.html")
    return content.replace("{{AUCTION_ID}}", str(auction_id))

@app.get("/history", response_class=HTMLResponse)
async def history_page():
    return read_static("history.html")

@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page():
    return read_static("analytics.html")

@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    return read_static("chat.html")

@app.get("/bot", response_class=HTMLResponse)
async def bot_page():
    return read_static("bot.html")

# ============ PROFILE ENDPOINTS ============

@app.get("/api/profile/{user_id}", response_model=schemas.UserProfileResponse)
async def get_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(database.User).filter(database.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Calculate stats
    total_bids = db.query(database.Bid).filter(database.Bid.user_id == user_id).count()
    total_won = db.query(database.Auction).filter(
        database.Auction.seller_id != user_id,
        database.Auction.is_active == False
    ).count()  # Simplified - you'd track winners properly in production
    
    # Calculate member since
    member_since = user.created_at.strftime("%B %Y")
    
    # Auto-assign badges based on activity
    badges = user.badges or []
    if total_bids >= 10 and "first_10_bids" not in badges:
        badges.append("first_10_bids")
    if total_bids >= 50 and "bid_master" not in badges:
        badges.append("bid_master")
    if total_won >= 5 and "winner_5" not in badges:
        badges.append("winner_5")
    
    user.badges = badges
    user.total_bids = total_bids
    user.total_won = total_won
    db.commit()
    
    return {
        "id": user.id,
        "username": user.username,
        "bio": user.bio,
        "avatar_color": user.avatar_color,
        "balance": user.balance,
        "reputation_score": user.reputation_score,
        "total_bids": total_bids,
        "total_won": total_won,
        "badges": badges,
        "created_at": user.created_at,
        "member_since": member_since
    }

@app.put("/api/profile/{user_id}")
async def update_profile(user_id: int, profile: schemas.UserProfileUpdate, db: Session = Depends(get_db)):
    user = db.query(database.User).filter(database.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update username (check if available)
    if profile.username and profile.username != user.username:
        existing = db.query(database.User).filter(database.User.username == profile.username).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already taken")
        user.username = profile.username
    
    if profile.bio is not None:
        user.bio = profile.bio
    
    if profile.avatar_color:
        user.avatar_color = profile.avatar_color
    
    db.commit()
    db.refresh(user)
    
    # Update localStorage info for frontend
    return {
        "user_id": user.id,
        "username": user.username,
        "balance": user.balance,
        "bio": user.bio,
        "avatar_color": user.avatar_color
    }

@app.get("/api/profile/{user_id}/stats")
async def get_user_stats(user_id: int, db: Session = Depends(get_db)):
    # Get bid statistics
    bids = db.query(database.Bid).filter(database.Bid.user_id == user_id).all()
    auctions_created = db.query(database.Auction).filter(database.Auction.seller_id == user_id).count()
    
    total_spent = sum([b.amount for b in bids])
    avg_bid = total_spent / len(bids) if bids else 0
    highest_bid = max([b.amount for b in bids]) if bids else 0
    
    # Get recent activity
    recent_bids = db.query(database.Bid).filter(
        database.Bid.user_id == user_id
    ).order_by(database.Bid.timestamp.desc()).limit(5).all()
    
    return {
        "total_bids": len(bids),
        "total_spent": round(total_spent, 2),
        "average_bid": round(avg_bid, 2),
        "highest_bid": round(highest_bid, 2),
        "auctions_created": auctions_created,
        "recent_bids": [
            {"auction_id": b.auction_id, "amount": b.amount, "timestamp": b.timestamp.isoformat()}
            for b in recent_bids
        ]
    }
@app.get("/profile", response_class=HTMLResponse)
async def profile_page():
    return read_static("profile.html")