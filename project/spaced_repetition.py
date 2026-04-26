"""SM-2 spaced repetition algorithm."""
from datetime import date, timedelta
from db import SessionLocal, Flashcard


def review(card_id: int, quality: int):
    """quality: 0..5 (0 = total blackout, 5 = perfect)."""
    db = SessionLocal()
    try:
        c = db.query(Flashcard).get(card_id)
        if not c:
            return None
        if quality < 3:
            c.repetitions = 0
            c.interval = 1
        else:
            if c.repetitions == 0:
                c.interval = 1
            elif c.repetitions == 1:
                c.interval = 6
            else:
                c.interval = int(round((c.interval or 1) * (c.ease or 2.5)))
            c.repetitions = (c.repetitions or 0) + 1
        c.ease = max(1.3, (c.ease or 2.5) + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
        c.due_date = date.today() + timedelta(days=c.interval)
        db.commit()
        return c
    finally:
        db.close()


def due_cards(user, deck: str | None = None):
    db = SessionLocal()
    try:
        q = db.query(Flashcard).filter(Flashcard.user_id == user.id, Flashcard.due_date <= date.today())
        if deck:
            q = q.filter(Flashcard.deck == deck)
        return q.order_by(Flashcard.due_date.asc()).all()
    finally:
        db.close()
