from sqlalchemy import Text

from app.models import ReviewRun


def test_review_engine_label_is_not_length_limited():
    column_type = ReviewRun.__table__.c.engine.type

    assert isinstance(column_type, Text)
    assert getattr(column_type, "length", None) is None
