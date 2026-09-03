import joblib
import os
import json
from groq import Groq
from dotenv import load_dotenv
import asyncio

load_dotenv()

MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'models')
try:
    price_model = joblib.load(os.path.join(MODEL_DIR, 'price_predictor.pkl'))
    fraud_model = joblib.load(os.path.join(MODEL_DIR, 'fraud_detector.pkl'))
    MODELS_LOADED = True
    print("✅ ML Models loaded successfully")
except Exception as e:
    MODELS_LOADED = False
    print(f"⚠️ Warning: ML Models not found. Running in mock mode. Error: {e}")

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def predict_price(starting_price, duration_hours):
    if not MODELS_LOADED:
        return starting_price * 1.5
    try:
        pred = price_model.predict([[starting_price, max(1, duration_hours)]])
        return round(float(pred[0]), 2)
    except:
        return round(starting_price * 1.5, 2)

def detect_fraud(amount, time_left, user_id):
    if not MODELS_LOADED:
        return False
    try:
        prob = fraud_model.predict_proba([[amount, max(1, time_left), user_id % 100]])[0][1]
        return prob > 0.5
    except:
        return False

async def analyze_item_groq(description: str):
    if not os.getenv("GROQ_API_KEY"):
        return {"risk_level": "unknown", "summary": "GROQ_API_KEY not set"}
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
            messages=[{
                "role": "user", 
                "content": f"Analyze this auction item for fraud risk. Return JSON: {{risk_level: 'low/med/high', summary: 'short text'}}. Item: {description}"
            }],
            model="groq/compound-mini",
            temperature=0.5,
            max_tokens=150,
            response_format={"type": "json_object"}
        ))
        
        raw_content = response.choices[0].message.content
        return json.loads(raw_content)
        
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON parse error: {e}")
        return {"risk_level": "unknown", "summary": "AI response malformed"}
    except Exception as e:
        print(f"⚠️ Groq API error: {e}")
        return {"risk_level": "error", "summary": str(e)}

async def chat_with_ai(message: str, context: str = ""):
    if not os.getenv("GROQ_API_KEY"):
        return "AI service unavailable. Please set GROQ_API_KEY"
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are AuctionIQ Assistant. Be helpful, concise, and friendly. Keep responses under 100 words."},
                {"role": "user", "content": f"Context: {context}\n\nQuestion: {message}"}
            ],
            model="groq/compound-mini",
            temperature=0.7,
            max_tokens=200
        ))
        return response.choices[0].message.content
    except Exception as e:
        return f"Sorry, I'm having trouble. Error: {str(e)}"