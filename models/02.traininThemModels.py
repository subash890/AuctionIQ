import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.metrics import mean_squared_error, accuracy_score
import joblib

def train_models():
    # 1. Price Prediction Model
    df_auctions = pd.read_csv('auctions.csv')
    X_price = df_auctions[['starting_price', 'duration_hours']]
    y_price = df_auctions['final_price']
    
    model_price = RandomForestRegressor()
    model_price.fit(X_price, y_price)
    joblib.dump(model_price, 'models/price_predictor.pkl')
    print("✅ Price Model Saved")

    # 2. Fraud Detection Model
    df_bids = pd.read_csv('bids.csv')
    X_fraud = df_bids[['bid_amount', 'time_left_minutes', 'user_id']]
    y_fraud = df_bids['is_fraud']
    
    model_fraud = RandomForestClassifier()
    model_fraud.fit(X_fraud, y_fraud)
    joblib.dump(model_fraud, 'models/fraud_detector.pkl')
    print("✅ Fraud Model Saved")

if __name__ == "__main__":
    import os
    os.makedirs('models', exist_ok=True)
    train_models()