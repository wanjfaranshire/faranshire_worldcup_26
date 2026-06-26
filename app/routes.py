from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import User, Match, Bet, KnockoutMatch
from app.forms import RegistrationForm, LoginForm
from datetime import datetime, timezone, timedelta
from flask import jsonify
from sqlalchemy.orm import joinedload

bp = Blueprint("main", __name__)

def get_now_utc():
    return datetime.now(timezone.utc)

def now_hkt():
    return datetime.now(timezone.utc) + timedelta(hours=8)

# Assuming your blueprint is named 'bp'
@bp.app_context_processor
def inject_navigation_stage():    
    HKT = timezone(timedelta(hours=8))
    switch_time = datetime(2026, 6, 28, 12, 0, 0, tzinfo=HKT)
    now = datetime.now(HKT)
    
    return {
        'is_knockout_stage': now >= switch_time
    }

# ====================== HOME ======================
@bp.route("/group")
def group_stage():
    # This route will ALWAYS show the group page, no redirect
    matches = Match.query.order_by(Match.date).all()
    from collections import defaultdict
    matches_by_day = defaultdict(list)
    for match in matches:
        day = match.date.date()
        matches_by_day[day].append(match)
        
    return render_template(
        "index.html", 
        matches=matches, 
        matches_by_day=matches_by_day, 
        now=now_hkt()
    )

@bp.route("/")
@bp.route("/index")
def index():
    # This route keeps the redirect logic for the "Home" button
    HKT = timezone(timedelta(hours=8))
    switch_time = datetime(2026, 6, 28, 12, 0, 0, tzinfo=HKT)
    if datetime.now(HKT) >= switch_time:
        return redirect(url_for("main.knockout"))
    
    # Otherwise, just call the group stage logic
    return group_stage()

# ====================== AUTH ======================
@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match.', 'warning')
            return redirect(url_for('main.register'))

        # ✅ Prevent duplicate username
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose another one.', 'warning')
            return redirect(url_for('main.register'))

        # Create new user
        new_user = User(
            username=username,
            password_hash=generate_password_hash(password),
            points=1000
        )
        db.session.add(new_user)
        db.session.commit()

        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('main.login'))

    return render_template('register.html')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)

            # === NEW: Redirect to Profile if first time ===
            if not user.nickname:   # If nickname is empty, assume first login
                flash('Welcome! Please complete your profile.', 'info')
                return redirect(url_for('main.profile'))

            return redirect(url_for('main.index'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.index"))


# ====================== BETTING ======================
@bp.route("/place_bet/<int:match_id>", methods=["POST"])
@login_required
def place_bet(match_id):
    from datetime import datetime, timezone
    current_utc = get_now_utc()

    match = Match.query.get_or_404(match_id)

    match_date = match.date
    if match_date.tzinfo is None:
        match_date = match_date.replace(tzinfo=timezone(timedelta(hours=8)))

    # Block if result already entered
    if match.result:
        flash("This match has already finished.", "danger")
        return redirect(url_for("main.index"))

    # Block if match time has already passed
    if match_date < current_utc:
        flash("This match has already started. You can no longer place or update bets.", "danger")
        return redirect(url_for("main.index"))

    home_score = request.form.get("home_score", type=int)
    away_score = request.form.get("away_score", type=int)
    new_stake = request.form.get("stake", type=int, default=50)

    if new_stake < 50:
        flash("Minimum stake is 50 points.", "danger")
        return redirect(url_for("main.index"))

    existing_bet = Bet.query.filter_by(
        user_id=current_user.id, match_id=match_id
    ).first()

    if existing_bet:
        # ====================== UPDATING EXISTING BET ======================
        old_stake = existing_bet.stake or 0
        difference = new_stake - old_stake

        if difference > 0:
            # Increasing stake
            if current_user.current_points < difference:
                flash("Not enough points to increase your bet!", "danger")
                return redirect(url_for("main.index"))
            current_user.points -= difference
        else:
            # Decreasing stake → refund the difference
            current_user.points += abs(difference)

        existing_bet.home_score = home_score
        existing_bet.away_score = away_score
        existing_bet.stake = new_stake
        existing_bet.points = 0

    else:
        # ====================== NEW BET ======================
        if current_user.current_points < new_stake:
            flash("Not enough points!", "danger")
            return redirect(url_for("main.index"))

        current_user.points -= new_stake

        bet = Bet(
            user_id=current_user.id,
            match_id=match_id,
            home_score=home_score,
            away_score=away_score,
            stake=new_stake,
            points=0,
        )
        db.session.add(bet)

    db.session.commit()
    flash("Bet placed / updated successfully!", "success")
    return redirect(url_for("main.index"))


@bp.route("/my_bets")
@login_required
def my_bets():
    from collections import defaultdict
    from datetime import datetime

    user_bets = Bet.query.filter_by(user_id=current_user.id).all()
    my_bets_by_day = defaultdict(list)

    for bet in user_bets:
        match = None
        if bet.match:                    # Group Stage
            match = bet.match
        elif bet.match_id:               # Knockout Stage
            knockout_match = KnockoutMatch.query.filter_by(match_number=bet.match_id).first()
            if knockout_match:
                match = knockout_match

        if match and match.date:
            day = match.date.date()
            my_bets_by_day[day].append(bet)
        else:
            day = datetime.now().date()
            my_bets_by_day[day].append(bet)

    sorted_bets_by_day = dict(sorted(my_bets_by_day.items()))

    # Pass knockout matches for rendering
    knockout_matches = {km.match_number: km for km in KnockoutMatch.query.all()}

    return render_template("my_bets.html",
                           bets=user_bets,                    # fixed: plural
                           my_bets_by_day=sorted_bets_by_day,
                           total_points=current_user.current_points,
                           knockout_matches=knockout_matches,
                           now=now_hkt())


@bp.route("/leaderboard")
def leaderboard():
    users = User.query.all()

    # Sort by dynamic current_points (most accurate)
    users = sorted(users, key=lambda u: u.current_points, reverse=True)

    return render_template("leaderboard.html", users=users)


from app.models import Bet, KnockoutMatch  # Ensure you have this import

@bp.route("/delete_bet/<int:bet_id>", methods=["POST"])
@login_required
def delete_bet(bet_id):
    bet = Bet.query.get_or_404(bet_id)

    if bet.user_id != current_user.id:
        flash("You can only delete your own bets.", "danger")
        return redirect(url_for("main.my_bets"))

    # Determine if the match is finished based on type
    is_finished = False
    
    # Check Group Stage
    if bet.match:
        if bet.match.result is not None:
            is_finished = True
    
    # Check Knockout Stage (using match_id as identifier)
    elif bet.match_id:
        km = KnockoutMatch.query.filter_by(match_number=bet.match_id).first()
        if km and km.is_completed:
            is_finished = True

    if is_finished:
        flash("Cannot delete bet on a finished match.", "danger")
        return redirect(url_for("main.my_bets"))

    # Refund the stake
    current_user.points += bet.stake or 50

    db.session.delete(bet)
    db.session.commit()

    flash("Bet deleted and stake refunded successfully.", "success")
    return redirect(url_for("main.my_bets"))


# ====================== HELPER: Get User's Bet for a Match (for index) ======================
# (Optional improvement)
@bp.app_template_filter("user_bet")
def get_user_bet(match, user):
    bet = next((b for b in match.bets if b.user_id == user.id), None)
    return bet.prediction if bet else None


# ====================== TEMPLATE HELPERS ======================
@bp.app_template_global("get_flag_code")
def get_flag_code(team_name):
    """Return country code for flagcdn.com"""
    flag_map = {
        "Mexico": "mx",
        "South Africa": "za",
        "Rep. of Korea": "kr",
        "Czech Rep.": "cz",
        "Canada": "ca",
        "Bosn. & Herz.": "ba",
        "USA": "us",
        "Paraguay": "py",
        "Brazil": "br",
        "Morocco": "ma",
        "Qatar": "qa",
        "Switzerland": "ch",
        "Haiti": "ht",
        "Scotland": "gb-sct",
        "Australia": "au",
        "Turkey": "tr",
        "Germany": "de",
        "Curaçao": "cw",
        "Netherlands": "nl",
        "Japan": "jp",
        "Ivory Coast": "ci",
        "Ecuador": "ec",
        "Sweden": "se",
        "Tunisia": "tn",
        "Spain": "es",
        "Cape Verde": "cv",
        "Belgium": "be",
        "Egypt": "eg",
        "Saudi Arabia": "sa",
        "Uruguay": "uy",
        "IR Iran": "ir",
        "New Zealand": "nz",
        "France": "fr",
        "Senegal": "sn",
        "Iraq": "iq",
        "Norway": "no",
        "Argentina": "ar",
        "Algeria": "dz",
        "Austria": "at",
        "Jordan": "jo",
        "Portugal": "pt",
        "DR Congo": "cd",
        "England": "gb-eng",
        "Croatia": "hr",
        "Ghana": "gh",
        "Panama": "pa",
        "Uzbekistan": "uz",
        "Colombia": "co",
        # Add more if needed
    }
    return flag_map.get(team_name, "xx")


# ====================== ADMIN - ENTER RESULTS ======================
@bp.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    if not current_user.is_admin:
        flash("Admin access required.", "danger")
        return redirect(url_for("main.index"))

    matches = Match.query.order_by(Match.date).all()

    from collections import defaultdict
    matches_by_day = defaultdict(list)
    for match in matches:
        day = match.date.date()
        matches_by_day[day].append(match)

    return render_template("admin.html", matches=matches, matches_by_day=matches_by_day)

@bp.route("/update_result/<int:match_id>", methods=["POST"])
@login_required
def update_result(match_id):
    if not current_user.is_admin:
        flash("Admin access required.", "danger")
        return redirect(url_for("main.admin"))

    match = Match.query.get_or_404(match_id)
    home = request.form.get("home_score", type=int)
    away = request.form.get("away_score", type=int)

    if home is None or away is None:
        flash("Invalid scores entered.", "danger")
        return redirect(url_for("main.admin"))

    match.result = f"{home} - {away}"

    # Calculate points using the method in Bet model (supports 2x and 1.5x)
    for bet in match.bets:
        bet.points = bet.calculate_points(home, away)

    db.session.commit()
    flash(f"Result updated for {match.team1} vs {match.team2}. Points awarded.", "success")
    return redirect(url_for("main.admin"))

@bp.route("/admin/delete_bet/<int:bet_id>", methods=["POST"])
@login_required
def admin_delete_bet(bet_id):
    if not current_user.is_admin:
        flash("Admin access required.", "danger")
        return redirect(url_for("main.admin"))

    bet = Bet.query.get_or_404(bet_id)
    user = bet.user

    # Refund the stake if the bet was active (no result yet)
    if not bet.match.result:
        user.points += bet.stake or 50

    db.session.delete(bet)
    db.session.commit()

    flash(f"Deleted bet for {bet.match.team1} vs {bet.match.team2}", "info")
    return redirect(url_for("main.admin"))

@bp.route("/clear_result/<int:match_id>", methods=["POST"])
def clear_result(match_id):
    if not current_user.is_authenticated:
        flash("Please login", "danger")
        return redirect(url_for("main.login"))

    match = Match.query.get_or_404(match_id)

    # Reset earned points but KEEP the bet record
    bets = Bet.query.filter_by(match_id=match_id).all()
    for bet in bets:
        bet.points = 0  # Remove the gain/loss

    match.result = None
    db.session.commit()

    flash(
        f"Result cleared for {match.team1} vs {match.team2}. Points restored.",
        "success",
    )
    return redirect(url_for("main.admin"))


# ==================== PROFILE ====================
@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.nickname = request.form.get("nickname")
        current_user.birthday = request.form.get("birthday")
        current_user.zodiac_sign = request.form.get("zodiac_sign")
        current_user.mbti = request.form.get("mbti")
        current_user.blood_type = request.form.get("blood_type")
        current_user.favourite_team = request.form.get("favourite_team")
        current_user.favourite_food = request.form.get("favourite_food")
        
        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for("main.profile"))

    all_bets = Bet.query.filter_by(user_id=current_user.id).all()

    group_history = [bet for bet in all_bets if bet.match]
    knockout_history = [bet for bet in all_bets if not bet.match]

    # Sorting (same as before)
    def group_sort_key(b):
        group_order = {'A':0,'B':1,'C':2,'D':3,'E':4,'F':5,'G':6,'H':7,'I':8,'J':9,'K':10,'L':11}
        group_val = b.match.group if b.match and b.match.group else 'Z'
        date_val = b.match.date if b.match and b.match.date else datetime.min
        return (group_order.get(group_val, 99), date_val)

    group_history.sort(key=group_sort_key)
    knockout_history.sort(key=lambda b: b.match_id or 0, reverse=True)

    knockout_matches = {km.match_number: km for km in KnockoutMatch.query.all()}

        # ====================== CORRECT POINTS HISTORY ======================
    import json
    from datetime import datetime
    from collections import defaultdict

    points_history = []
    current_points = 1000

    # Starting point + bonuses
    bonus_total = 0
    bonus_desc = ""
    if getattr(current_user, 'bonus_claimed', False):
        bonus_total += 1000
        bonus_desc += " + Gold Bonus"
    if getattr(current_user, 'bread_bonus_claimed', False):
        bonus_total += 500
        bonus_desc += " + Bread"
    if getattr(current_user, 'pancake_bonus_claimed', False):
        bonus_total += 200
        bonus_desc += " + Pancake"
    if getattr(current_user, 'lomo_bonus_claimed', False):
        bonus_total += 300
        bonus_desc += " + Lomo"

    current_points += bonus_total
    points_history.append({
        "date": "Start",
        "points": current_points,
        "tooltip": f"Starting Points{bonus_desc} (+{bonus_total})"
    })

    # Group by date - include ALL finished bets (win or lose)
    daily_results = defaultdict(list)

    sorted_bets = sorted(all_bets, key=lambda b: 
        (b.match.date if b.match and b.match.date else 
         (knockout_matches.get(b.match_id).date if knockout_matches.get(b.match_id) else datetime.min)))

    for bet in sorted_bets:
        # Check if match is finished
        is_finished = False
        if bet.match and bet.match.result is not None:
            is_finished = True
        elif not bet.match:
            km = knockout_matches.get(bet.match_id)
            if km and km.is_completed:
                is_finished = True

        if is_finished:
            stake = bet.stake or 50
            net = (bet.points or 0) - stake

            if bet.match:
                match_name = f"{bet.match.team1} vs {bet.match.team2}"
            else:
                km = knockout_matches.get(bet.match_id)
                match_name = f"{km.team1 or 'TBD'} vs {km.team2 or 'TBD'}" if km else f"Knockout {bet.match_id}"

            date_str = (bet.match.date.strftime('%Y-%m-%d') if bet.match and bet.match.date else 
                       (knockout_matches.get(bet.match_id).date.strftime('%Y-%m-%d') if knockout_matches.get(bet.match_id) else "Unknown"))
            
            daily_results[date_str].append({
                "match": match_name,
                "net": net
            })

    # Build graph points
    for date_str in sorted(daily_results.keys()):
        actions = daily_results[date_str]
        daily_net = sum(a['net'] for a in actions)
        current_points += daily_net

        tooltip_lines = [f"{a['match']} {'+' if a['net'] > 0 else ''}{a['net']}" for a in actions]

        points_history.append({
            "date": date_str,
            "points": current_points,
            "tooltip": "\n".join(tooltip_lines)
        })

    return render_template("profile.html",
                           group_history=group_history,
                           knockout_history=knockout_history,
                           knockout_matches=knockout_matches,
                           total_points=current_user.current_points,
                           points_history=json.dumps(points_history))


# ==================== USER PROFILE API (for modal) ====================
@bp.route('/api/user_profile/<int:user_id>')
@login_required
def user_profile_api(user_id):
    user = User.query.get_or_404(user_id)
    all_bets = Bet.query.filter_by(user_id=user.id).all()
    
    knockout_map = {km.match_number: km for km in KnockoutMatch.query.all()}
    
    group_history = []
    knockout_history = []
    wins = 0
    losses = 0

    for bet in all_bets:
        # 1. Group Stage Logic
        if bet.match and bet.match.result is not None:
            outcome = "WIN" if (bet.points and bet.points > 0) else "LOSE"
            if outcome == "WIN": wins += 1
            else: losses += 1
            
            group_history.append({
                "group": bet.match.group,
                "date": bet.match.date, # Keep for sorting
                "match": f"{bet.match.team1} vs {bet.match.team2}",
                "your_bet": f"{bet.home_score} - {bet.away_score}",
                "match_result": bet.match.result,
                "outcome": outcome
            })

        # 2. Knockout Stage Logic
        elif bet.match_id in knockout_map and knockout_map[bet.match_id].is_completed:
            km = knockout_map[bet.match_id]
            outcome = "WIN" if (bet.points and bet.points > 0) else "LOSE"
            if outcome == "WIN": wins += 1
            else: losses += 1
            
            penalty_str = ""
            if km.home_penalty is not None and km.away_penalty is not None:
                penalty_str = f" ({km.home_penalty} - {km.away_penalty})"

            knockout_history.append({
                "match_id": km.match_number, # Keep for sorting
                "round": km.round_name,
                "match": f"{km.team1 or 'TBD'} vs {km.team2 or 'TBD'}",
                "your_bet": f"{bet.home_score} - {bet.away_score}",
                "match_result": f"{km.home_score} - {km.away_score}{penalty_str}",
                "outcome": outcome
            })

    # === Apply Sorting to match profile.html logic ===
    
    # Sort Group: by Group (A-L) then by Date
    group_order = {'A':0,'B':1,'C':2,'D':3,'E':4,'F':5,'G':6,'H':7,'I':8,'J':9,'K':10,'L':11}
    group_history.sort(key=lambda x: (group_order.get(x['group'], 99), x['date']))

    # Sort Knockout: newest match_id first
    knockout_history.sort(key=lambda x: x['match_id'], reverse=True)

    data = {
        "username": user.username,
        "nickname": user.nickname,
        "birthday": user.birthday,
        "zodiac_sign": user.zodiac_sign,
        "blood_type": user.blood_type,
        "mbti": user.mbti,
        "favourite_team": user.favourite_team,
        "favourite_food": user.favourite_food,
        "total_points": user.current_points,
        # ADD THESE TWO LINES:
        "wins": wins,
        "losses": losses,
        # -------------------
        "group_history": group_history,
        "knockout_history": knockout_history
    }
    return jsonify(data)


@bp.route('/api/match_bets/<int:match_id>')
@login_required
def match_bets_api(match_id):
    # Try to find as Group Stage Match first (by id)
    match = Match.query.get(match_id)
    
    if not match:
        # Try as Knockout Match (by match_number)
        match = KnockoutMatch.query.filter_by(match_number=match_id).first()

    if not match:
        return jsonify({"error": "Match not found"}), 404

    # Get bets using the stored match_id (which is match_number for knockout)
    bets = Bet.query.filter_by(match_id=match_id).all()

    bet_list = []
    for bet in bets:
        bet_list.append({
            "username": bet.user.username,
            "home_score": bet.home_score,
            "away_score": bet.away_score,
            "stake": bet.stake,
            "points": bet.points if getattr(match, 'result', None) or getattr(match, 'is_completed', False) else None
        })

    # Build nice match name
    if hasattr(match, 'match_number'):   # KnockoutMatch
        match_name = f"Match {match.match_number} - {match.team1 or match.home_placeholder} vs {match.team2 or match.away_placeholder}"
    else:  # Group Stage
        match_name = f"{match.team1} vs {match.team2}"

    return jsonify({
        "match": match_name,
        "total_bets": len(bet_list),
        "bets": bet_list
    })

@bp.route('/how-to-play')
def how_to_play():
    return render_template('how_to_play.html')

@bp.route('/make-admin')
@login_required
def make_admin():
    # Option 1: Make the currently logged-in user an admin
    current_user.is_admin = True
    db.session.commit()
    
    flash(f"You are now an admin! ({current_user.username})", "success")
    return redirect(url_for('main.admin'))

@bp.route('/claim-bonus', methods=['POST'])
@login_required
def claim_bonus():
    if current_user.bonus_claimed:
        flash("You have already claimed the bonus!", "warning")
        return redirect(url_for('main.how_to_play'))

    current_user.points += 1000
    current_user.bonus_claimed = True
    db.session.commit()

    # Redirect with query param to trigger confetti
    return redirect(url_for('main.how_to_play', claimed='true'))

@bp.route('/seed')
def seed_database():
    try:
        from app.models import Match
        import pandas as pd
        from datetime import datetime

        db.create_all()

        Match.query.delete()
        db.session.commit()

        # Try to load the Excel file
        df = pd.read_excel('group_schedule.xlsx')

        count = 0
        for _, row in df.iterrows():
            try:
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
                count += 1
            except Exception as inner_e:
                print(f"Skipped row: {inner_e}")

        db.session.commit()
        return f"✅ Successfully seeded {count} matches from Excel!"

    except Exception as e:
        return f"❌ Seeding Error: {str(e)}"

@bp.route("/seed-knockout")
@login_required
def seed_knockout():
    if not current_user.is_admin:
        flash("Admin access required.", "danger")
        return redirect(url_for("main.index"))
    
    try:
        from seed_knockout import seed_knockout
        seed_knockout()
        flash("✅ Knockout stage seeded successfully! (Check db-check)", "success")
        return redirect(url_for("main.db_check"))   # or admin_knockout
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        full_trace = traceback.format_exc()
        print("SEED ERROR:", full_trace)   # This will appear in Render Logs
        flash(f"❌ Seeding failed: {error_msg}", "danger")
        return f"""
        <h2>Seeding Error</h2>
        <pre>{full_trace}</pre>
        <a href="/db-check">Back to DB Check</a>
        """, 500

@bp.route('/db-check')
def db_check():
    try:
        from app.models import Match, User, Bet
        import sqlalchemy as sa

        match_count = Match.query.count()
        user_count = User.query.count()
        bet_count = Bet.query.count()

        return f"""
        <h2>Database Check</h2>
        <p>✅ Tables exist!</p>
        <ul>
            <li>Matches: {match_count}</li>
            <li>Users: {user_count}</li>
            <li>Bets: {bet_count}</li>
        </ul>
        """
    except Exception as e:
        return f"❌ Error: {str(e)}"

@bp.route('/claim-bread-bonus', methods=['POST'])
@login_required
def claim_bread_bonus():
    if getattr(current_user, 'bread_bonus_claimed', False):
        return "You've already claimed the secret faranshire! 🍞"

    current_user.points += 500
    current_user.bread_bonus_claimed = True
    db.session.commit()

    return "🍞 Secret Faranshire Bonus claimed! +500 points added to your account!"

@bp.route('/db-migrate')
def db_migrate():
    db.create_all()
    return """
        <h2>✅ Database Migration Successful!</h2>
        <p>New columns have been added.</p>
        <p><a href="/">Go back to Home</a></p>
    """

@bp.route('/claim-pancake-bonus', methods=['POST'])
@login_required
def claim_pancake_bonus():
    if getattr(current_user, 'pancake_bonus_claimed', False):
        return "You've already claimed this bonus!"

    current_user.points += 200
    current_user.pancake_bonus_claimed = True
    db.session.commit()

    return "🥞 Secret Pancake Bonus claimed! +200 points added!"

@bp.route('/claim-lomo-bonus', methods=['POST'])
@login_required
def claim_lomo_bonus():
    if getattr(current_user, 'lomo_bonus_claimed', False):
        return "You've already claimed this bonus!"

    current_user.points += 300
    current_user.lomo_bonus_claimed = True
    db.session.commit()

    return "🤱 Secret lomo Bonus claimed! +300 points added!"

# ==================== KNOCKOUT STAGE ADMIN ====================

@bp.route('/admin/knockout')
@login_required
def admin_knockout():
    if not current_user.is_admin:
        flash("Admin access required.", "danger")
        return redirect(url_for('main.index'))
    
    all_knockout = KnockoutMatch.query.order_by(KnockoutMatch.date, KnockoutMatch.match_number).all()
    
    # Debug info
    print("Total Knockout Matches:", len(all_knockout))
    for m in all_knockout[:10]:   # print first 10
        print(m.round_name, m.match_number, m.team1, m.team2)
    
    round32_matches = [m for m in all_knockout if str(m.round_name).strip().lower() == "round of 32"]
    print("Round of 32 found:", len(round32_matches))
    
    # Get teams
    all_teams_query = db.session.query(Match.team1).distinct().union(
        db.session.query(Match.team2).distinct()).all()
    all_teams = sorted([t[0] for t in all_teams_query if t[0]])
    
    return render_template('admin_knockout.html', 
                           all_knockout_matches=all_knockout,
                           round32_matches=round32_matches,
                           now=now_hkt(),
                           all_teams=all_teams)


# ==================== KNOCKOUT STAGE ADMIN ROUTES ====================

@bp.route('/admin/knockout/update_team/<int:match_id>', methods=['POST'])
@login_required
def update_knockout_team(match_id):
    """Update one or both teams in Round of 32"""
    if not current_user.is_admin:
        flash("Admin access required.", "danger")
        return redirect(url_for('main.admin_knockout'))
   
    match = KnockoutMatch.query.get_or_404(match_id)
   
    team1 = request.form.get('team1', '').strip()
    team2 = request.form.get('team2', '').strip()
   
    # At least one team must be selected
    if not team1 and not team2:
        flash("Please select at least one team to update.", "danger")
        return redirect(url_for('main.admin_knockout'))
   
    # Check if user is trying to set the same team for both sides
    if team1 and team2 and team1 == team2:
        flash("Cannot select the same team for both sides.", "danger")
        return redirect(url_for('main.admin_knockout'))
   
    # Check duplicate across Round of 32 (only for teams being changed)
    existing = KnockoutMatch.query.filter(
        KnockoutMatch.round_name.ilike("round of 32"),
        KnockoutMatch.id != match_id
    ).all()
   
    used = set()
    for m in existing:
        if m.team1: used.add(m.team1)
        if m.team2: used.add(m.team2)
   
    if team1 and team1 in used:
        flash("This team is already assigned to another Round of 32 match.", "danger")
        return redirect(url_for('main.admin_knockout'))
   
    if team2 and team2 in used:
        flash("This team is already assigned to another Round of 32 match.", "danger")
        return redirect(url_for('main.admin_knockout'))
   
    # === UPDATE ONLY THE TEAMS THAT WERE SELECTED ===
    if team1:
        match.team1 = team1
    if team2:
        match.team2 = team2
   
    db.session.commit()
    flash(f"Teams updated for Match {match.match_number}", "success")
    return redirect(url_for('main.admin_knockout'))


@bp.route('/admin/knockout/clear_teams/<int:match_id>', methods=['POST'])
@login_required
def clear_knockout_teams(match_id):
    """Clear teams + full cascade clear downstream"""
    if not current_user.is_admin:
        flash("Admin access required.", "danger")
        return redirect(url_for('main.admin_knockout'))
    
    match = KnockoutMatch.query.get_or_404(match_id)
    
    def clear_downstream(current_match):
        current_match.team1 = None
        current_match.team2 = None
        current_match.team1_code = None
        current_match.team2_code = None
        current_match.home_score = None
        current_match.away_score = None
        current_match.home_penalty = None
        current_match.away_penalty = None
        current_match.winner = None
        current_match.winner_code = None
        current_match.is_completed = False
        
        if current_match.next_match_id:
            next_m = KnockoutMatch.query.filter_by(match_number=current_match.next_match_id).first()
            if next_m:
                clear_downstream(next_m)
    
    clear_downstream(match)
    db.session.commit()
    flash(f"Cleared teams and all subsequent matches starting from Match {match.match_number}", "success")
    return redirect(url_for('main.admin_knockout'))


@bp.route('/admin/knockout/update_result/<int:match_id>', methods=['POST'])
@login_required
def update_knockout_result(match_id):
    if not current_user.is_admin:
        flash("Admin access required.", "danger")
        return redirect(url_for('main.admin_knockout'))
   
    match = KnockoutMatch.query.get_or_404(match_id)
   
    match.home_score = request.form.get('home_score', type=int)
    match.away_score = request.form.get('away_score', type=int)
    match.home_penalty = request.form.get('home_penalty', type=int)
    match.away_penalty = request.form.get('away_penalty', type=int)
   
    winner = match.calculate_winner()
   
    if winner:
        match.is_completed = True
        match.winner = winner
        match.winner_code = match.team1_code if winner == match.team1 else match.team2_code
       
        # === CALCULATE AND AWARD POINTS TO BETTORS ===
        # Use match_number because that's what we store in Bet for knockout
        bets = Bet.query.filter_by(match_id=match.match_number).all()
        
        for bet in bets:
            if bet.home_score is not None and bet.away_score is not None:
                bet.points = match.calculate_knockout_points(
                    bet.home_score, 
                    bet.away_score, 
                    bet.stake
                )

        # === NORMAL BRACKET ADVANCE ===
        if match.next_match_id:
            next_match = KnockoutMatch.query.filter_by(match_number=match.next_match_id).first()
            if next_match:
                if match.is_home_in_next:
                    next_match.team1 = winner
                    next_match.team1_code = match.winner_code
                else:
                    next_match.team2 = winner
                    next_match.team2_code = match.winner_code
       
        # === THIRD PLACE PLAY-OFF LOGIC (M103) ===
        if match.round_name.lower() == "semifinal":
            loser = match.team1 if winner == match.team2 else match.team2
            loser_code = match.team1_code if winner == match.team2 else match.team2_code
           
            third_place = KnockoutMatch.query.filter_by(match_number=103).first()
            if third_place:
                if match.match_number == 101: # Loser of M101 → Home in M103
                    third_place.team1 = loser
                    third_place.team1_code = loser_code
                elif match.match_number == 102: # Loser of M102 → Away in M103
                    third_place.team2 = loser
                    third_place.team2_code = loser_code
               
                flash(f"Result saved. {winner} advanced. Loser {loser} to Third Place Play-off. Points awarded.", "success")
            else:
                flash(f"Result saved. Winner: {winner}. Points awarded.", "success")
        else:
            flash(f"Result saved. Winner: {winner}. Points awarded to bettors.", "success")
    else:
        flash("Result saved (incomplete).", "warning")
   
    db.session.commit()
    return redirect(url_for('main.admin_knockout'))

@bp.route('/admin/knockout/debug')
@login_required
def knockout_debug():
    if not current_user.is_admin:
        return "Admin only", 403
    matches = KnockoutMatch.query.order_by(KnockoutMatch.round_name, KnockoutMatch.match_number).all()
    
    output = "<h2>Knockout Debug View</h2><table border=1 cellpadding=5>"
    output += "<tr><th>Round</th><th>Match</th><th>Team1</th><th>Team2</th><th>Score</th><th>Winner</th><th>Next ID</th></tr>"
    
    for m in matches:
        score = f"{m.home_score}-{m.away_score}" if m.home_score is not None else "-"
        output += f"<tr><td>{m.round_name}</td><td>{m.match_number}</td><td>{m.team1 or '-'}</td><td>{m.team2 or '-'}</td><td>{score}</td><td><b>{m.winner or '-'}</b></td><td>{m.is_completed}</td><td>{m.next_match_id or '-'}</td></tr>"
    output += "</table>"
    return output

@bp.route('/time-debug')
def time_debug():
    from datetime import timezone # Ensure this is imported
    matches = Match.query.limit(5).all()
    current_utc = get_now_utc()
    
    output = f"""
    <h2>Time Debug</h2>
    <p>Server now (UTC): {current_utc}</p>
    <table border="1">
        <tr><th>Match</th><th>Origin Date</th><th>UTC Date</th><th>Origin is pass</th><th>utc Is Past?</th></tr>
    """
    for m in matches:
        # 1. Force the database date to be aware (if it isn't already)
        m_date = m.date
        if m_date.tzinfo is None:
            m_date_origin = m_date.replace(tzinfo=timezone(timedelta(hours=8)))
            m_date_utc = m_date.replace(tzinfo=timezone.utc)
            
        # 2. Now compare two aware objects
        is_past_origin = m_date_origin < current_utc
        is_past_utc = m_date_utc < current_utc
        
        output += f"<tr><td>{m.team1} vs {m.team2}</td><td>{m_date_origin}</td>td><td>{m_date_utc}</td><td>{is_past_origin}</td><td>{is_past_utc}</td></tr>"
    output += "</table>"
    return output

# ====================== PUBLIC KNOCKOUT BRACKET ======================
@bp.route("/knockout")
def knockout():
    all_knockout = KnockoutMatch.query.order_by(
        KnockoutMatch.date, KnockoutMatch.match_number
    ).all()

    from collections import defaultdict
    knockout_by_round = defaultdict(list)
    knockout_by_day = defaultdict(list)

    for match in all_knockout:
        round_name = match.round_name.strip()
        knockout_by_round[round_name].append(match)
        
        # Group by date for "By Date" view
        day = match.date.date()
        knockout_by_day[day].append(match)

    # Sort rounds
    round_order = ["Round of 32", "Round of 16", "Quarterfinal", "Semifinal", "Third Place", "Final"]
    sorted_rounds = {r: knockout_by_round[r] for r in round_order if r in knockout_by_round}

    return render_template("knockout.html", 
                           knockout_by_round=sorted_rounds,
                           knockout_by_day=knockout_by_day,
                           Bet=Bet,
                           now=now_hkt())

# ====================== KNOCKOUT STAGE BETTING ======================
@bp.route("/place_bet_knockout/<int:match_number>", methods=["POST"])
@login_required
def place_bet_knockout(match_number):
    from datetime import timezone, timedelta
    current_utc = get_now_utc()

    match = KnockoutMatch.query.filter_by(match_number=match_number).first_or_404()

    match_date = match.date
    if match_date.tzinfo is None:
        match_date = match_date.replace(tzinfo=timezone(timedelta(hours=8)))

    if match.is_completed:
        flash("This match has already finished.", "danger")
        return redirect(url_for("main.knockout"))

    if match_date < current_utc:
        flash("This match has already started. You can no longer place or update bets.", "danger")
        return redirect(url_for("main.knockout"))

    try:
        home_score = request.form.get("home_score", type=int)
        away_score = request.form.get("away_score", type=int)
        new_stake = request.form.get("stake", type=int, default=50)

        if new_stake < 50 or home_score is None or away_score is None:
            flash("Please enter valid scores and stake (min 50).", "danger")
            return redirect(url_for("main.knockout"))

        # Strict balance check
        if current_user.current_points < new_stake:
            flash(f"Not enough points! You currently have {current_user.current_points} points.", "danger")
            return redirect(url_for("main.knockout"))

        # Use match_id = match_number for knockout bets
        existing_bet = Bet.query.filter_by(
            user_id=current_user.id, 
            match_id=match_number
        ).first()

        if existing_bet:
            # Update existing bet
            old_stake = existing_bet.stake or 0
            difference = new_stake - old_stake

            if difference > 0:
                # Increasing stake
                if current_user.current_points < difference:
                    flash("Not enough points to increase stake!", "danger")
                    return redirect(url_for("main.knockout"))
                current_user.points -= difference
            else:
                # Decreasing stake → refund
                current_user.points += abs(difference)

            existing_bet.home_score = home_score
            existing_bet.away_score = away_score
            existing_bet.stake = new_stake
        else:
            # New bet
            current_user.points -= new_stake

            bet = Bet(
                user_id=current_user.id,
                match_id=match_number,          # ← Using match_number as match_id
                home_score=home_score,
                away_score=away_score,
                stake=new_stake,
                points=0,
            )
            db.session.add(bet)

        db.session.commit()
        flash("✅ Bet placed / updated successfully!", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"❌ Failed to save bet: {str(e)}", "danger")
        print(f"KNOCKOUT BET ERROR: {str(e)}")

    return redirect(url_for("main.knockout"))


from sqlalchemy import text

@bp.route('/db-fix-bet-fk')
@login_required
def db_fix_bet_fk():
    if not current_user.is_admin:
        return "Admin only", 403
    
    try:
        # Drop the foreign key constraint
        db.session.execute(text("""
            ALTER TABLE bet 
            DROP CONSTRAINT IF EXISTS bet_match_id_fkey;
        """))
        
        # Allow match_id to be NULL
        db.session.execute(text("""
            ALTER TABLE bet 
            ALTER COLUMN match_id DROP NOT NULL;
        """))
        
        db.session.commit()
        
        return """
        <h2>✅ Success!</h2>
        <p>Foreign key constraint removed.</p>
        <p>PostgreSQL will now accept knockout match numbers.</p>
        <br>
        <a href="/seed-knockout" class="btn btn-success">→ Run Knockout Seeder Now</a>
        """
    except Exception as e:
        db.session.rollback()
        return f"<h2>Error</h2><pre>{str(e)}</pre>"


@bp.route('/db-remove-fk')
@login_required
def db_remove_fk():
    if not current_user.is_admin:
        return "Admin only", 403
    try:
        db.session.execute(text("ALTER TABLE bet DROP CONSTRAINT IF EXISTS bet_match_id_fkey;"))
        db.session.execute(text("ALTER TABLE bet ALTER COLUMN match_id DROP NOT NULL;"))
        db.session.commit()
        return "<h2>✅ Foreign Key Removed. You can now use match_id for knockout too.</h2>"
    except Exception as e:
        return f"Error: {e}"

