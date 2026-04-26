"""Vercel entry point. Vercel's @vercel/python runtime looks for `app`."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app  # noqa: F401
