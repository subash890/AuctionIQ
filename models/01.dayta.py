import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

def generate_data():
    # 1. Generate Auctions
    n_auctions = 1000
    auctions = {
        'auction_id': range(1, n_auctions + 1),
        'category': random.choices(['Electronics', 'Art', 'Car', 'Fashion'], k=n_auctions),
        'starting_price': np.random.uniform(10, 1000, n_auctions),
        'duration_hours': np.random.randint(1, 24, n_auctions),
        'final_price': [] 
    }
    
    # 2. Generate Bids & Calculate Final Price (Target for ML)
    bids_data = []
    for i in range(n_auctions):
        start = auctions['starting_price'][i]
        # Logic: Final price is usually 1.5x to 3x starting price
        final = start * np.random.uniform(1.5, 3.0)
        auctions['final_price'].append(final)
        
        # Generate bid history for this auction
        n_bids = random.randint(5, 50)
        for b in range(n_bids):
            bids_data.append({
                'auction_id': i + 1,
                'bid_amount': start + (final - start) * (b / n_bids) * np.random.uniform(0.8, 1.2),
                'time_left_minutes': random.randint(1, 1440),
                'user_id': random.randint(1, 100),
                'is_fraud': 1 if random.random() < 0.05 else 0 # 5% fraud rate
            })
            
    pd.DataFrame(auctions).to_csv('auctions.csv', index=False)
    pd.DataFrame(bids_data).to_csv('bids.csv', index=False)
    print("✅ Data generated.")

if __name__ == "__main__":
    generate_data()