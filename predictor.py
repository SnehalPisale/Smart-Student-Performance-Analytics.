"""Performance prediction: Random Forest regression + rule-based risk levels."""
import json
import os
from datetime import datetime, timedelta

import pandas as pd
from flask import current_app
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

import analytics
import repository as repo

FEATURES = ["internal1", "internal2", "assignment", "attendance_pct"]


def _info_path():
    return os.path.join(os.path.dirname(current_app.config["DATABASE"]), "model_info.json")


def load_model_info():
    try:
        with open(_info_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def risk_level(score, attendance):
    cfg = current_app.config
    att = 100.0 if attendance is None or pd.isna(attendance) else attendance
    if score < cfg["HIGH_SCORE"] or att < cfg["HIGH_ATTENDANCE"]:
        return "High"
    if score < cfg["MEDIUM_SCORE"] or att < cfg["MEDIUM_ATTENDANCE"]:
        return "Medium"
    return "Low"


def run_prediction():
    cfg = current_app.config
    df = analytics.load_frame()
    if df.empty:
        raise ValueError("There are no marks to analyse yet. Enter or upload marks first.")

    X = df[FEATURES].copy()
    X = X.fillna(X.median()).fillna(0)
    labelled = df["final_mark"].notna()
    n_labelled = int(labelled.sum())
    info = {"features": FEATURES, "labelled_rows": n_labelled, "total_rows": int(len(df))}

    if n_labelled >= cfg["MIN_TRAIN_ROWS"]:
        X_lab, y_lab = X[labelled], df.loc[labelled, "final_mark"]
        X_tr, X_te, y_tr, y_te = train_test_split(X_lab, y_lab, test_size=0.2, random_state=42)
        model = RandomForestRegressor(n_estimators=200, max_depth=8, min_samples_leaf=2,
                                      random_state=42)
        model.fit(X_tr, y_tr)
        info["r2"] = round(float(r2_score(y_te, model.predict(X_te))), 3)
        info["mae"] = round(float(mean_absolute_error(y_te, model.predict(X_te))), 2)
        model.fit(X_lab, y_lab)                       # refit on all labelled rows
        predicted = pd.Series(model.predict(X), index=df.index)
        predicted[labelled] = df.loc[labelled, "final_mark"]   # outcome already known
        info["method"] = "Random Forest (200 trees)"
        info["importances"] = {f: round(float(v), 3)
                               for f, v in zip(FEATURES, model.feature_importances_)}
    else:
        predicted = 0.85 * (0.35 * X["internal1"] + 0.35 * X["internal2"]
                            + 0.30 * X["assignment"]) + 0.15 * X["attendance_pct"]
        info["method"] = (f"Weighted formula (fewer than {cfg['MIN_TRAIN_ROWS']} rows with final "
                          "marks, so the model was not trained)")
        info["r2"] = info["mae"] = info["importances"] = None

    df["predicted"] = predicted.clip(0, 100)
    per_student = df.groupby("student_id").agg(predicted=("predicted", "mean"),
                                               attendance=("attendance_pct", "mean"))
    now = datetime.now().replace(microsecond=0)
    last = repo.last_run_time()
    if last and now <= datetime.strptime(last, "%Y-%m-%d %H:%M:%S"):
        now = datetime.strptime(last, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=1)  # keep runs distinct
    stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    rows = [(int(sid), round(float(r.predicted), 1), risk_level(r.predicted, r.attendance))
            for sid, r in per_student.iterrows()]
    repo.save_predictions(rows, stamp)

    info["trained_at"] = stamp
    info["students"] = len(rows)
    info["counts"] = {lvl: sum(1 for _, _, r in rows if r == lvl) for lvl in ("Low", "Medium", "High")}
    with open(_info_path(), "w", encoding="utf-8") as fh:
        json.dump(info, fh)
    return info
