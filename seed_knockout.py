import pandas as pd
from app import create_app, db
from app.models import KnockoutMatch

app = create_app()
app.app_context().push()

def seed_knockout():
    print("🔄 Resetting and seeding Knockout Stage...")

    # Drop and recreate the table to add new columns
    KnockoutMatch.__table__.drop(db.engine, checkfirst=True)
    KnockoutMatch.__table__.create(db.engine)

    # Load data
    df_schedule = pd.read_excel('knockout_schedule.xlsx', sheet_name='Sheet1')
    df_placeholders = pd.read_excel('knockout_schedule.xlsx', sheet_name='Sheet3')

    # Placeholder mapping
    placeholder_map = {}
    for _, row in df_placeholders.iterrows():
        match_num = str(row['match_number']).strip().lower().replace('m', '')
        placeholder_map[match_num] = {
            'home': row.get('home_placeholder'),
            'away': row.get('away_placeholder')
        }

    count = 0
    for _, row in df_schedule.iterrows():
        match_num_str = str(row['match_number']).strip().lower().replace('m', '')
        placeholders = placeholder_map.get(match_num_str, {})

        next_id = row.get('next_match_id')
        if pd.notna(next_id):
            next_id_str = str(next_id).strip().lower().replace('m', '')
            try:
                next_match_id = int(next_id_str)
            except:
                next_match_id = None
        else:
            next_match_id = None

        match = KnockoutMatch(
            round_name=str(row['round_name']).strip(),
            match_number=int(match_num_str),
            home_placeholder=placeholders.get('home'),
            away_placeholder=placeholders.get('away'),
            date=pd.to_datetime(row['date'], errors='coerce'),
            venue=str(row.get('venue', '')),
            next_match_id=next_match_id,
            is_home_in_next=bool(row.get('is_home_in_next', True))
        )
        db.session.add(match)
        count += 1

    db.session.commit()
    print(f"✅ Successfully seeded {count} knockout matches!")

if __name__ == "__main__":
    seed_knockout()