import sys
import os

# Ensure the app can import local modules
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from web.main import app
from apig_wsgi import make_lambda_handler

handler = make_lambda_handler(app)
