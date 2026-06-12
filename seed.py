import os
from app import create_app, db
from app.models import Match
from datetime import datetime, timezone
import pandas as pd

# Create instance folder if it doesn't exist
if not os.path.exists('instance'):
    os.makedirs('instance')

app = create_app()

with app.app_context():
    db.create_all()

    # Clear existing matches
    Match.query.delete()
    db.session.commit()
    
    df = pd.read_excel('group_schedule.xlsx')
    
    count = 0
    for _, row in df.iterrows():
        # Combine date and time
        match_date = pd.to_datetime(row['date']).date()
        match_time = pd.to_datetime(row['time']).time()
        
        # Create naive datetime first
        naive_dt = datetime.combine(match_date, match_time)
        
        # Convert to UTC (this is the key change)
        utc_dt = naive_dt.replace(tzinfo=timezone.utc)
        
        group = str(row.get('team1_code', ''))[0] if str(row.get('team1_code', '')) else None
        
        match = Match(
            team1=row['team1'],
            team2=row['team2'],
            date=utc_dt,                    # ← Stored in UTC
            stage="Group Stage",
            group=group,
            venue=row.get('venue', '')
        )
        db.session.add(match)
        count += 1
    
    db.session.commit()
    print(f"✅ Successfully loaded {count} group stage matches in UTC!")