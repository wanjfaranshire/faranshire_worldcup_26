import os
from app import create_app, db
from app.models import Match
from datetime import datetime
import pandas as pd

# Create instance folder if it doesn't exist
if not os.path.exists('instance'):
    os.makedirs('instance')

app = create_app()

with app.app_context():
    # Create all tables if they don't exist
    db.create_all()

    # Now it's safe to delete and seed
    Match.query.delete()
    db.session.commit()
    
    df = pd.read_excel('group_schedule.xlsx')
    
    for _, row in df.iterrows():
        match_date = pd.to_datetime(row['date'])
        match_time = pd.to_datetime(row['time'])
        full_date = datetime.combine(match_date.date(), match_time.time())
        
        group = str(row.get('team1_code', ''))[0] if str(row.get('team1_code', '')) else None
        
        match = Match(
            team1=row['team1'],
            team2=row['team2'],
            date=full_date,
            stage="Group Stage",
            group=group,
            venue=row.get('venue', '')
        )
        db.session.add(match)
    
    db.session.commit()
    print(f"✅ Loaded {len(df)} matches with groups!")