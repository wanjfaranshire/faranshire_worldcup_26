import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'super-secret-key-change-this')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///worldcup.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False