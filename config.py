import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-before-deploying")
    DATABASE = os.environ.get(
        "DATABASE_PATH", os.path.join(BASE_DIR, "instance", "student_analytics.db")
    )
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads"))
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024          # 2 MB upload cap
    ALLOWED_EXTENSIONS = {"csv", "xlsx"}
    MAX_UPLOAD_ROWS = 5000
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Academic rules (all marks are out of 100)
    PASS_MARK = 40
    # Risk rules applied to each student's predicted score and average attendance
    HIGH_SCORE = 45
    MEDIUM_SCORE = 60
    HIGH_ATTENDANCE = 65
    MEDIUM_ATTENDANCE = 75
    # Minimum labelled (final-mark) rows needed to train the Random Forest
    MIN_TRAIN_ROWS = 30
