from datetime import date, timedelta


def apply_sm2(card, quality: int):
    """quality: 0..5"""
    if quality < 3:
        card.repetitions = 0
        card.interval = 1
    else:
        if card.repetitions == 0:
            card.interval = 1
        elif card.repetitions == 1:
            card.interval = 6
        else:
            card.interval = int(round((card.interval or 1) * (card.ease or 2.5)))
        card.repetitions = (card.repetitions or 0) + 1
    card.ease = max(1.3, (card.ease or 2.5) + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
    card.due_date = date.today() + timedelta(days=card.interval)
    return card
