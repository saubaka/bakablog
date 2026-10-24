"""gunicorn entry point:  gunicorn -w 2 --threads 4 wsgi:app"""
from app import create_app

app = create_app()
