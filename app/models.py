from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    points = db.Column(db.Integer, default=1000)
    is_admin = db.Column(db.Boolean, default=False)

    bets = db.relationship('Bet', back_populates='user', lazy=True)

    @property
    def current_points(self):
        earned = sum(bet.points or 0 for bet in self.bets)
        return self.points + earned

    # Add these fields inside the User class
    nickname = db.Column(db.String(80))
    birthday = db.Column(db.String(20))
    zodiac_sign = db.Column(db.String(20))
    blood_type = db.Column(db.String(5))
    mbti = db.Column(db.String(10))
    favourite_team = db.Column(db.String(80))
    favourite_food = db.Column(db.String(120))
    bonus_claimed = db.Column(db.Boolean, default=False)
    bread_bonus_claimed = db.Column(db.Boolean, default=False)
    pancake_bonus_claimed = db.Column(db.Boolean, default=False)
    lomo_bonus_claimed = db.Column(db.Boolean, default=False)


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team1 = db.Column(db.String(100), nullable=False)
    team2 = db.Column(db.String(100), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    stage = db.Column(db.String(50), default="Group Stage")
    group = db.Column(db.String(10))
    venue = db.Column(db.String(100))
    result = db.Column(db.String(20))

    bets = db.relationship('Bet', back_populates='match', lazy=True)


class Bet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'), nullable=False)
    
    home_score = db.Column(db.Integer, nullable=True)
    away_score = db.Column(db.Integer, nullable=True)
    stake = db.Column(db.Integer, default=50)
    points = db.Column(db.Integer, default=0)

    user = db.relationship('User', back_populates='bets')
    match = db.relationship('Match', back_populates='bets')


    def calculate_points(self, actual_home, actual_away):
        if self.home_score is None or self.away_score is None:
            return 0
        stake = self.stake or 50

        if self.home_score == actual_home and self.away_score == actual_away:
            return int(stake * 2)

        user_win = 1 if self.home_score > self.away_score else 0 if self.home_score == self.away_score else 2
        actual_win = 1 if actual_home > actual_away else 0 if actual_home == actual_away else 2

        if user_win == actual_win:
            return int(stake * 1.5)

        return 0


class KnockoutMatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    round_name = db.Column(db.String(60), nullable=False)
    match_number = db.Column(db.Integer, nullable=False)
    
    # Placeholders from Sheet3 (e.g. "1E", "3ABCDF")
    home_placeholder = db.Column(db.String(20), nullable=True)
    away_placeholder = db.Column(db.String(20), nullable=True)
    
    # Actual teams
    team1 = db.Column(db.String(100), nullable=True)
    team2 = db.Column(db.String(100), nullable=True)
    team1_code = db.Column(db.String(10), nullable=True)
    team2_code = db.Column(db.String(10), nullable=True)
    
    date = db.Column(db.DateTime, nullable=True)
    venue = db.Column(db.String(100), nullable=True)
    
    home_score = db.Column(db.Integer, nullable=True)
    away_score = db.Column(db.Integer, nullable=True)
    home_penalty = db.Column(db.Integer, nullable=True)
    away_penalty = db.Column(db.Integer, nullable=True)
    
    winner = db.Column(db.String(100), nullable=True)
    winner_code = db.Column(db.String(10), nullable=True)
    is_completed = db.Column(db.Boolean, default=False)
    
    next_match_id = db.Column(db.Integer, nullable=True)
    is_home_in_next = db.Column(db.Boolean, default=True)
    
    def calculate_winner(self):
        if self.home_score is None or self.away_score is None:
            return None
            
        if self.home_score > self.away_score:
            self.winner = self.team1
            self.winner_code = self.team1_code
        elif self.away_score > self.home_score:
            self.winner = self.team2
            self.winner_code = self.team2_code
        else:
            # Penalty shootout
            if self.home_penalty is not None and self.away_penalty is not None:
                if self.home_penalty > self.away_penalty:
                    self.winner = self.team1
                    self.winner_code = self.team1_code
                else:
                    self.winner = self.team2
                    self.winner_code = self.team2_code
        return self.winner