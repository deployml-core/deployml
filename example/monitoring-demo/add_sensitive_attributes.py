#!/usr/bin/env python3
"""Add sensitive attributes to existing prediction logs for fairness monitoring"""

from sqlalchemy import create_engine, text
import random

DATABASE_URL = "postgresql://mlflow:Ctda.zQ55WInAl0a@34.169.7.44:5432/metrics"
engine = create_engine(DATABASE_URL)

# Sample values for sensitive attributes
buyer_age_groups = ["25-35", "35-45", "45-55", "55+"]
locations = ["urban", "suburban", "rural"]
first_time_buyer_values = [True, False]

with engine.connect() as conn:
    # Get all existing predictions
    result = conn.execute(text("SELECT id, features FROM prediction_logs"))
    predictions = result.fetchall()
    
    print(f"\n📋 Found {len(predictions)} prediction logs")
    print("=" * 60)
    
    # Update each prediction with random sensitive attributes
    for pred_id, features in predictions:
        # Generate random sensitive attributes
        new_attrs = {
            'buyer_age_group': random.choice(buyer_age_groups),
            'location': random.choice(locations),
            'first_time_buyer': random.choice(first_time_buyer_values)
        }
        
        # Merge with existing features
        import json
        updated_features = dict(features)
        updated_features.update(new_attrs)
        
        # Update the database
        update_query = text("""
            UPDATE prediction_logs 
            SET features = :updated_features
            WHERE id = :pred_id
        """)
        
        conn.execute(update_query, {
            'pred_id': pred_id,
            'updated_features': json.dumps(updated_features)
        })
        
        print(f"  ✅ Updated prediction {pred_id} with: {new_attrs}")
    
    conn.commit()
    print("=" * 60)
    print(f"✅ Updated all {len(predictions)} predictions with sensitive attributes!\n")
    
    # Show updated records
    print("\n📊 Updated Prediction Logs:")
    print("=" * 60)
    result = conn.execute(text("SELECT id, features FROM prediction_logs LIMIT 5"))
    for pred_id, features in result:
        print(f"\nID {pred_id}:")
        print(f"  Features: {features}")
    print("=" * 60)

