import os
import uuid
import zipfile
import random
from io import BytesIO
from datetime import datetime
from functools import wraps
from flask import (
    Flask, request, jsonify, render_template, send_from_directory,
    redirect, url_for, flash, session, send_file
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate

from models import db, User, Upload, Badge, Challenge
from analyzers import analyze_file
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ----------------- Setup -----------------
ROOT = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(ROOT, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = "super-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB

db.init_app(app)
migrate = Migrate(app, db)

with app.app_context():
    db.create_all()

# --- In-memory token store ---
TOKENS = {}

# ----------------- Helpers -----------------
def auth_required(f):
    """Decorator for API token auth."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token or token not in TOKENS:
            return jsonify({"msg": "Unauthorized"}), 401
        request.user_id = TOKENS[token]
        return f(*args, **kwargs)
    return wrapper

def update_user_score(user_id):
    user = User.query.get(user_id)
    uploads = Upload.query.filter_by(user_id=user_id).all()
    user.score = sum([(u.score or 0.0) for u in uploads]) / len(uploads) if uploads else 0.0
    db.session.commit()

def award_badge(user, name, desc):
    if not Badge.query.filter_by(user_id=user.id, name=name).first():
        b = Badge(user_id=user.id, name=name, description=desc)
        db.session.add(b)
        db.session.commit()

def maybe_award_badge(user, score, talent_type):
    if score >= 90:
        award_badge(user, "Gold Star", f"Score >= 90 in {talent_type}")
    elif score >= 75:
        award_badge(user, "Silver Star", f"Score >= 75 in {talent_type}")

    uploads = Upload.query.filter_by(user_id=user.id).order_by(Upload.created_at.desc()).limit(3).all()
    if len(uploads) >= 2 and uploads[0].score and uploads[1].score:
        if uploads[0].score > uploads[1].score + 5:
            award_badge(user, "Improver", "Notable score improvement")

# ----------------- Pages -----------------
@app.route("/")
def index():
    return render_template("home.html")

@app.route("/upload_page")
def upload_page():
    return render_template("upload.html")

@app.route("/results")
def results_page():
    return render_template("results.html")

# ----------------- Auth Pages -----------------
@app.route("/register", methods=["GET", "POST"])
def register_page():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("Username and password are required", "danger")
            return redirect(url_for("register_page"))

        if User.query.filter_by(username=username).first():
            flash("Username already exists", "danger")
            return redirect(url_for("register_page"))

        user = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            flash("Login successful!", "success")
            return redirect(url_for("dashboard_page"))

        flash("Invalid username or password", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))

# ----------------- Dashboard -----------------
@app.route("/dashboard")
def dashboard_page():
    if "user_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    uploads = Upload.query.filter_by(user_id=user.id).all()
    badges = Badge.query.filter_by(user_id=user.id).all()

    return render_template("dashboard.html", user=user, uploads=uploads, badges=badges)

@app.route("/badges")
def badges_page():
    badges_data = Badge.query.all()
    badge_list = [
        {"name": b.name, "image": f"{b.name.lower().replace(' ', '_')}.png", "description": b.description}
        for b in badges_data
    ]
    return render_template("badges.html", badges=badge_list)

# ----------------- API -----------------
@app.route("/api/login", methods=["POST"])
def api_login():
    try:
        data = request.get_json() or {}
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return jsonify({"msg": "⚠️ Username and password required"}), 400

        user = User.query.filter_by(username=username).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"msg": "❌ Invalid username or password"}), 401

        token = str(uuid.uuid4())  # Generate token
        TOKENS[token] = user.id
        session["user_id"] = user.id

        return jsonify({
            "token": token,
            "user_id": user.id,
            "redirect": "/dashboard",
            "msg": "✅ Login successful"
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "msg": "🚨 Server error. Please try again later.",
            "error": str(e)
        }), 500

@app.route("/api/upload", methods=["POST"])
@auth_required
def api_upload():
    try:
        user_id = request.user_id

        if "file" not in request.files:
            return jsonify({"msg": "No file uploaded"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"msg": "No file selected"}), 400

        filename = secure_filename(file.filename)
        save_name = f"{user_id}_{int(datetime.utcnow().timestamp())}_{filename}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], save_name)
        file.save(save_path)

        # Call AI analyzer
        score, feedback = analyze_file(save_path, request.form.get("talent_type", "general"))

        upl = Upload(user_id=user_id, filename=save_name, talent_type=request.form.get("talent_type"), score=score, feedback=feedback)
        db.session.add(upl)
        db.session.commit()

        update_user_score(user_id)
        maybe_award_badge(User.query.get(user_id), score, request.form.get("talent_type"))

        # Store in session for results page
        session["last_result"] = {
            "file_url": f"/uploads/{save_name}",
            "score": score,
            "ai_feedback": feedback,
            "improvement_tips": ["Practice daily", "Stay confident"] if score < 85 else [],
            "leaderboard": [
                {"rank": 1, "name": "Alice", "score": 95},
                {"rank": 2, "name": "Bob", "score": 90},
                {"rank": 3, "name": "You", "score": score}
            ]
        }

        return jsonify({"msg": "Upload successful", "redirect": "/results", "score": score, "feedback": feedback}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"msg": "Server error", "error": str(e)}), 500

@app.route("/api/results")
def api_results():
    result = session.get("last_result")
    if not result:
        return jsonify({"msg": "No results available"}), 404
    return jsonify(result)

# ----------------- Download Features -----------------
@app.route("/uploads/<path:fname>")
def uploaded_file(fname):
    return send_from_directory(app.config["UPLOAD_FOLDER"], fname)

@app.route("/download_report")
def download_report():
    score = request.args.get("score", "N/A")
    username = "Student"

    pdf_buffer = BytesIO()
    p = canvas.Canvas(pdf_buffer, pagesize=A4)
    width, height = A4

    p.setFont("Helvetica-Bold", 20)
    p.drawString(100, height - 100, "SkillShine Performance Report")

    p.setFont("Helvetica", 14)
    p.drawString(100, height - 150, f"Name: {username}")
    p.drawString(100, height - 180, f"Score: {score}/100")

    p.setFont("Helvetica", 12)
    p.drawString(100, height - 220, "AI Feedback:")
    p.setFont("Helvetica-Oblique", 12)
    p.drawString(120, height - 240, "Keep practicing, improve lighting & clarity.")

    p.setFont("Helvetica", 12)
    p.drawString(100, height - 280, "Leaderboard (Top Performers):")
    leaderboard = [("Aarav", 95), ("Kriti", 88), ("Rohan", 80)]
    y = height - 300
    for i, (name, sc) in enumerate(leaderboard, 1):
        p.drawString(120, y, f"{i}. {name} — {sc}")
        y -= 20

    p.showPage()
    p.save()

    pdf_buffer.seek(0)
    return send_file(pdf_buffer, as_attachment=True, download_name="SkillShine_Report.pdf", mimetype="application/pdf")

@app.route("/download_all_uploads")
def download_all_uploads():
    if "user_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    uploads = Upload.query.filter_by(user_id=user.id).all()

    if not uploads:
        flash("No uploads to download.", "info")
        return redirect(url_for("dashboard_page"))

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for upl in uploads:
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], upl.filename)
            if os.path.exists(file_path):
                zipf.write(file_path, arcname=upl.filename)

    zip_buffer.seek(0)
    return send_file(zip_buffer, as_attachment=True, download_name="My_Uploads.zip", mimetype="application/zip")

if __name__ == "__main__":
    app.run(debug=True)
