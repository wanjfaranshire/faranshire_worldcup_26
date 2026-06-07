from app import create_app, db
from app.models import Match
from datetime import datetime
import pandas as pd

app = create_app()

with app.app_context():
    Match.query.delete()
    db.session.commit()
    
    df = pd.read_excel('group_schedule.xlsx')
    
    for _, row in df.iterrows():
        # Parse date and time
        match_date = pd.to_datetime(row['date'])
        match_time = pd.to_datetime(row['time'])
        full_date = datetime.combine(match_date.date(), match_time.time())
        
        # Get group from team code (e.g. "A1" -> "A")
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