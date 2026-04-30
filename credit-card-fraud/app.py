"""
app.py - Flask application entry point.
"""
import os, json, io, time
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, session, send_file, flash)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pandas as pd
import numpy as np

from utils import (load_dataset, preprocess, risk_level,
                   explain_prediction, load_model, DATASET_PATH, FEATURE_COLS,
                   NUMERIC_COLS, CATEGORICAL_COLS, BINARY_COLS, TARGET_COL)
from train import train_all

app = Flask(__name__)
app.secret_key = os.environ.get("FRAUDSHIELD_SECRET", "fraud_detection_secret_2024")

UPLOAD_FOLDER   = os.path.dirname(__file__)
ALLOWED_EXT     = {"csv", "xlsx", "xls"}
SUSPICIOUS_LOG  = os.path.join(os.path.dirname(__file__), "suspicious_log.json")
HISTORY_LOG     = os.path.join(os.path.dirname(__file__), "prediction_history.json")
USERS_FILE      = os.path.join(os.path.dirname(__file__), "users.json")

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ── User store helpers ────────────────────────────────────────────────────────
def load_users() -> dict:
    """Return {username: {password_hash, role, created_at}} dict."""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE) as f:
            return json.load(f)
    # Seed default admin on first run
    default = {
        os.environ.get("FRAUDSHIELD_USER", "admin"): {
            "password_hash": generate_password_hash(
                os.environ.get("FRAUDSHIELD_PASS", "admin123")
            ),
            "role": "admin",
            "created_at": datetime.now().isoformat(),
        }
    }
    save_users(default)
    return default


def save_users(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

# ── Login rate limiting (in-memory) ──────────────────────────────────────────
_login_attempts = {}
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300


def check_rate_limit(ip):
    now = time.time()
    rec = _login_attempts.get(ip, {"count": 0, "first": now, "locked_until": 0})
    if now < rec.get("locked_until", 0):
        remaining = int(rec["locked_until"] - now)
        return False, f"Too many attempts. Try again in {remaining}s."
    if now - rec["first"] > LOCKOUT_SECONDS:
        rec = {"count": 0, "first": now, "locked_until": 0}
    return True, None


def record_failed_login(ip):
    now = time.time()
    rec = _login_attempts.get(ip, {"count": 0, "first": now, "locked_until": 0})
    if now - rec["first"] > LOCKOUT_SECONDS:
        rec = {"count": 0, "first": now, "locked_until": 0}
    rec["count"] += 1
    if rec["count"] >= MAX_ATTEMPTS:
        rec["locked_until"] = now + LOCKOUT_SECONDS
    _login_attempts[ip] = rec


def clear_login_attempts(ip):
    _login_attempts.pop(ip, None)


# ── Auth helpers ──────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def load_suspicious():
    if os.path.exists(SUSPICIOUS_LOG):
        with open(SUSPICIOUS_LOG) as f:
            return json.load(f)
    return []


def save_suspicious(entry):
    log = load_suspicious()
    log.append(entry)
    with open(SUSPICIOUS_LOG, "w") as f:
        json.dump(log, f, indent=2)


def load_history():
    if os.path.exists(HISTORY_LOG):
        with open(HISTORY_LOG) as f:
            return json.load(f)
    return []


def save_history(entry):
    log = load_history()
    log.append(entry)
    # Keep last 500 predictions
    if len(log) > 500:
        log = log[-500:]
    with open(HISTORY_LOG, "w") as f:
        json.dump(log, f, indent=2)


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = request.remote_addr
        ok, msg = check_rate_limit(ip)
        if not ok:
            flash(msg, "error")
            return render_template("login.html")

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        users = load_users()

        if username in users and check_password_hash(users[username]["password_hash"], password):
            session["logged_in"] = True
            session["username"]  = username
            session["role"]      = users[username].get("role", "user")
            clear_login_attempts(ip)
            return redirect(url_for("dashboard"))

        record_failed_login(ip)
        flash("Invalid username or password", "error")
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username    = request.form.get("username", "").strip()
        email       = request.form.get("email", "").strip()
        password    = request.form.get("password", "")
        confirm     = request.form.get("confirm_password", "")

        # Validation
        if not username or not password or not email:
            flash("All fields are required.", "error")
            return render_template("signup.html")

        if len(username) < 3 or len(username) > 32:
            flash("Username must be 3–32 characters.", "error")
            return render_template("signup.html")

        if not username.isalnum() and not all(c.isalnum() or c in "_-" for c in username):
            flash("Username can only contain letters, numbers, _ and -", "error")
            return render_template("signup.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("signup.html")

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("signup.html")

        users = load_users()
        if username in users:
            flash("Username already taken. Choose another.", "error")
            return render_template("signup.html")

        # Save new user
        users[username] = {
            "password_hash": generate_password_hash(password),
            "email": email,
            "role": "user",
            "created_at": datetime.now().isoformat(),
        }
        save_users(users)
        flash("Account created! You can now sign in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Inject session info into every template ───────────────────────────────────
@app.context_processor
def inject_user():
    return {
        "current_user": session.get("username", ""),
        "current_role": session.get("role", "user"),
        "is_admin": session.get("role") == "admin",
    }


@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/predict_page")
@login_required
def predict_page():
    return render_template("predict.html")


@app.route("/alerts")
@login_required
def alerts():
    log = load_suspicious()
    return render_template("alerts.html", alerts=log[::-1])


@app.route("/admin")
@login_required
def admin_panel():
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))
    users = load_users()
    history = load_history()
    suspicious = load_suspicious()

    # Build per-user stats from history
    user_stats = {}
    for entry in history:
        u = entry.get("predicted_by", "—")
        if u not in user_stats:
            user_stats[u] = {"total": 0, "fraud": 0}
        user_stats[u]["total"] += 1
        if entry.get("label") == "Fraud":
            user_stats[u]["fraud"] += 1

    # Sanitize users for template (no password hashes)
    safe_users = []
    for uname, info in users.items():
        safe_users.append({
            "username": uname,
            "email": info.get("email", "—"),
            "role": info.get("role", "user"),
            "created_at": info.get("created_at", "—")[:10] if info.get("created_at") else "—",
            "predictions": user_stats.get(uname, {}).get("total", 0),
            "fraud_found": user_stats.get(uname, {}).get("fraud", 0),
        })

    return render_template("admin.html",
        users=safe_users,
        total_users=len(users),
        total_predictions=len(history),
        total_alerts=len(suspicious),
    )


@app.route("/api/admin/promote", methods=["POST"])
@login_required
def api_promote_user():
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    data = request.get_json()
    username = data.get("username", "").strip()
    new_role = data.get("role", "user")
    if new_role not in ("admin", "user"):
        return jsonify({"error": "Invalid role"}), 400
    users = load_users()
    if username not in users:
        return jsonify({"error": "User not found"}), 404
    if username == session.get("username"):
        return jsonify({"error": "Cannot change your own role"}), 400
    users[username]["role"] = new_role
    save_users(users)
    return jsonify({"status": "ok", "username": username, "role": new_role})


@app.route("/api/admin/delete_user", methods=["POST"])
@login_required
def api_delete_user():
    if session.get("role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    data = request.get_json()
    username = data.get("username", "").strip()
    if username == session.get("username"):
        return jsonify({"error": "Cannot delete yourself"}), 400
    users = load_users()
    if username not in users:
        return jsonify({"error": "User not found"}), 404
    del users[username]
    save_users(users)
    return jsonify({"status": "ok"})


# ── API: dataset stats ────────────────────────────────────────────────────────
@app.route("/api/stats")
@login_required
def api_stats():
    try:
        df = load_dataset()
        total      = len(df)
        fraud_cnt  = int(df[TARGET_COL].sum()) if TARGET_COL in df.columns else 0
        legit_cnt  = total - fraud_cnt
        fraud_rate = round(fraud_cnt / total * 100, 2) if total else 0

        # Fraud by hour
        by_hour = {}
        if "transaction_hour" in df.columns and TARGET_COL in df.columns:
            grp = df[df[TARGET_COL] == 1].groupby("transaction_hour").size()
            by_hour = {int(k): int(v) for k, v in grp.items()}

        # Fraud by merchant
        by_merchant = {}
        if "merchant_category" in df.columns and TARGET_COL in df.columns:
            grp = df[df[TARGET_COL] == 1].groupby("merchant_category").size()
            by_merchant = {str(k): int(v) for k, v in grp.items()}

        # Amount distribution
        fraud_amounts = df[df[TARGET_COL] == 1]["amount"].tolist() if TARGET_COL in df.columns else []
        legit_amounts = df[df[TARGET_COL] == 0]["amount"].tolist() if TARGET_COL in df.columns else []

        # Fraud by age group
        by_age = {}
        if "cardholder_age" in df.columns and TARGET_COL in df.columns:
            bins = [0, 25, 35, 45, 55, 65, 120]
            age_labels = ["<25", "25-34", "35-44", "45-54", "55-64", "65+"]
            age_groups = pd.cut(df["cardholder_age"], bins=bins, labels=age_labels)
            fraud_mask = df[TARGET_COL] == 1
            grp = age_groups[fraud_mask].value_counts().sort_index()
            by_age = {str(k): int(v) for k, v in grp.items()}

        # Avg fraud amount vs legit
        avg_fraud_amt = round(float(df[df[TARGET_COL] == 1]["amount"].mean()), 2) if fraud_cnt else 0
        avg_legit_amt = round(float(df[df[TARGET_COL] == 0]["amount"].mean()), 2) if legit_cnt else 0

        # Preview
        preview = df.head(10).fillna("").to_dict(orient="records")

        return jsonify({
            "total": total,
            "fraud": fraud_cnt,
            "legit": legit_cnt,
            "fraud_rate": fraud_rate,
            "columns": list(df.columns),
            "by_hour": by_hour,
            "by_merchant": by_merchant,
            "by_age": by_age,
            "fraud_amounts": fraud_amounts[:500],
            "legit_amounts": legit_amounts[:500],
            "avg_fraud_amount": avg_fraud_amt,
            "avg_legit_amount": avg_legit_amt,
            "preview": preview,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: model results ────────────────────────────────────────────────────────
@app.route("/api/model_results")
@login_required
def api_model_results():
    _, meta = load_model()
    if meta is None:
        return jsonify({"error": "Model not trained yet"}), 404
    results = meta.get("results", {})
    importances = meta.get("importances", {})
    return jsonify({
        "best_model": meta.get("best_model_name"),
        "results": results,
        "importances": importances,
    })


# ── API: train ────────────────────────────────────────────────────────────────
@app.route("/api/train", methods=["POST"])
@login_required
def api_train():
    if session.get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403
    try:
        strategy = request.json.get("strategy", "smote") if request.is_json else "smote"
        meta = train_all(balance_strategy=strategy)
        return jsonify({"status": "ok", "best_model": meta["best_model_name"],
                        "results": meta["results"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: predict ──────────────────────────────────────────────────────────────
@app.route("/api/predict", methods=["POST"])
@login_required
def api_predict():
    try:
        model, meta = load_model()
        if model is None:
            return jsonify({"error": "Model not trained. Please train first."}), 400

        data = request.get_json()
        scaler        = meta["scaler"]
        encoders      = meta["encoders"]
        feature_names = meta["feature_names"]

        cat_cols = set(encoders.keys())
        row = {}
        for col in feature_names:
            if col in cat_cols:
                row[col] = 0.0
            else:
                row[col] = float(data.get(col, 0))

        for col, le in encoders.items():
            if col in feature_names:
                val = str(data.get(col, le.classes_[0]))
                row[col] = float(le.transform([val])[0]) if val in le.classes_ else 0.0

        df_row = pd.DataFrame([row])[feature_names]
        num_cols = [c for c in NUMERIC_COLS if c in df_row.columns]
        df_row[num_cols] = scaler.transform(df_row[num_cols])

        prob  = float(model.predict_proba(df_row)[0][1])
        label = "Fraud" if prob >= 0.5 else "Legitimate"
        rl    = risk_level(prob)
        reasons = explain_prediction(data, prob)

        result = {
            "label": label,
            "probability": round(prob * 100, 2),
            "risk_level": rl,
            "reasons": reasons,
            "model_used": meta.get("best_model_name", "Unknown"),
            "timestamp": datetime.now().isoformat(),
            "predicted_by": session.get("username", "unknown"),
        }

        # Save to history
        history_entry = {**data, **result}
        save_history(history_entry)

        # Save high-risk to alerts log
        if rl == "High":
            save_suspicious(history_entry)

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: batch predict from CSV ───────────────────────────────────────────────
@app.route("/api/batch_predict", methods=["POST"])
@login_required
def api_batch_predict():
    try:
        model, meta = load_model()
        if model is None:
            return jsonify({"error": "Model not trained. Please train first."}), 400

        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if not allowed_file(file.filename):
            return jsonify({"error": "Invalid file type"}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        if ext in (".xlsx", ".xls"):
            df = pd.read_excel(file)
        else:
            df = pd.read_csv(file)

        scaler        = meta["scaler"]
        encoders      = meta["encoders"]
        feature_names = meta["feature_names"]

        # Encode categoricals
        for col, le in encoders.items():
            if col in df.columns:
                df[col] = df[col].astype(str).apply(
                    lambda v: float(le.transform([v])[0]) if v in le.classes_ else 0.0
                )

        available = [c for c in feature_names if c in df.columns]
        X = df[available].fillna(0)
        num_cols = [c for c in NUMERIC_COLS if c in X.columns]
        X[num_cols] = scaler.transform(X[num_cols])

        probs  = model.predict_proba(X)[:, 1]
        labels = ["Fraud" if p >= 0.5 else "Legitimate" for p in probs]
        risks  = [risk_level(p) for p in probs]

        df["prediction"]  = labels
        df["probability"] = [round(p * 100, 2) for p in probs]
        df["risk_level"]  = risks

        buf = io.StringIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        return send_file(
            io.BytesIO(buf.getvalue().encode()),
            mimetype="text/csv",
            as_attachment=True,
            download_name="batch_predictions.csv"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: prediction history ───────────────────────────────────────────────────
@app.route("/api/history")
@login_required
def api_history():
    log = load_history()
    return jsonify({"history": log[::-1][:100]})


# ── API: clear alerts ─────────────────────────────────────────────────────────
@app.route("/api/alerts/clear", methods=["POST"])
@login_required
def api_clear_alerts():
    with open(SUSPICIOUS_LOG, "w") as f:
        json.dump([], f)
    return jsonify({"status": "ok"})


# ── API: upload dataset ───────────────────────────────────────────────────────
@app.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    if session.get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "" or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Use CSV or XLSX."}), 400
    filename = secure_filename(file.filename)
    dest = os.path.join(app.config["UPLOAD_FOLDER"], "dataset" + os.path.splitext(filename)[1])
    file.save(dest)
    import utils
    utils.DATASET_PATH = dest
    return jsonify({"status": "ok", "filename": filename})


# ── API: export CSV ───────────────────────────────────────────────────────────
@app.route("/api/export/csv")
@login_required
def export_csv():
    df = load_dataset()
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return send_file(io.BytesIO(buf.getvalue().encode()),
                     mimetype="text/csv",
                     as_attachment=True,
                     download_name="fraud_report.csv")


# ── API: export PDF ───────────────────────────────────────────────────────────
@app.route("/api/export/pdf")
@login_required
def export_pdf():
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet

        df = load_dataset()
        _, meta = load_model()

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph("FraudShield — Fraud Detection Report", styles["Title"]))
        elements.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
        elements.append(Spacer(1, 12))

        total = len(df)
        fraud = int(df[TARGET_COL].sum()) if TARGET_COL in df.columns else 0
        summary_data = [
            ["Metric", "Value"],
            ["Total Transactions", str(total)],
            ["Fraud Transactions", str(fraud)],
            ["Legitimate Transactions", str(total - fraud)],
            ["Fraud Rate", f"{round(fraud/total*100,2)}%"],
        ]
        if meta:
            summary_data.append(["Best Model", meta.get("best_model_name", "N/A")])

        t = Table(summary_data, colWidths=[250, 200])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE",   (0, 0), (-1, -1), 10),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))

        fraud_df = df[df[TARGET_COL] == 1].head(20) if TARGET_COL in df.columns else df.head(20)
        cols = list(fraud_df.columns)
        rows = [cols] + fraud_df.fillna("").values.tolist()
        rows = [[str(c) for c in r] for r in rows]
        t2 = Table(rows)
        t2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e94560")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("GRID",       (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("FONTSIZE",   (0, 0), (-1, -1), 7),
        ]))
        elements.append(Paragraph("Sample Fraud Transactions", styles["Heading2"]))
        elements.append(t2)

        doc.build(elements)
        buf.seek(0)
        return send_file(buf, mimetype="application/pdf",
                         as_attachment=True, download_name="fraud_report.pdf")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: simulate real-time transaction ──────────────────────────────────────
@app.route("/api/simulate")
@login_required
def api_simulate():
    import random
    merchants = ["Electronics", "Travel", "Grocery", "Restaurant", "Online", "ATM"]
    tx = {
        "amount":              round(random.uniform(1, 2000), 2),
        "transaction_hour":    random.randint(0, 23),
        "merchant_category":   random.choice(merchants),
        "foreign_transaction": random.randint(0, 1),
        "location_mismatch":   random.randint(0, 1),
        "device_trust_score":  random.randint(0, 100),
        "velocity_last_24h":   random.randint(0, 10),
        "cardholder_age":      random.randint(18, 80),
    }
    return jsonify(tx)


if __name__ == "__main__":
    if not os.path.exists(os.path.join(os.path.dirname(__file__), "model.pkl")):
        print("🔄 No model found — training now...")
        try:
            train_all()
        except Exception as e:
            print(f"⚠️  Auto-train failed: {e}")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
