# Start a new chat (for /api/messages/start)

from flask import (
    Flask, request, jsonify, render_template, session,
    redirect, url_for, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import uuid
import json
import os
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Fix session cookie for local dev (so session doesn't disappear)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False
)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DATA_FILE = "data_store.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    else:
        return {
            "users": [],
            "posts": [],
            "stories": [],
            "ads": [],
            "messages": [],
            "notifications": []
        }

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data_store, f, indent=2)

data_store = load_data()

def find_user(username):
    if not username:
        return None
    return next((u for u in data_store["users"] if u["username"] == username), None)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Login required"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated

@app.route("/")
def home():
    return redirect(url_for("login_page"))

@app.route("/register-page")
def register_page():
    return render_template("sign_up.html")

@app.route("/login-page")
def login_page():
    return render_template("index.html")

@app.route("/register", methods=["POST"])
def register():
    global data_store
    data_store = load_data()  # ensure fresh data

    data = request.get_json() or {}
    username = (data.get("username") or "").lower().strip()  # normalize
    email = (data.get("email") or "").lower().strip()
    name = data.get("name", "").strip()
    password = data.get("password", "")
    co_password = data.get("co_password", "")
    country = data.get("country", "")
    national_id = data.get("national_id")
    province = data.get("province")
    passport_no = data.get("passport_no")
    country_name = data.get("country_name")
    dob = data.get("dob")
    phone = data.get("phone")

    if not all([username, name, password, co_password, dob, phone, country]):
        return jsonify(success=False, message="Fill all required fields"), 400

    if password != co_password:
        return jsonify(success=False, message="Passwords do not match"), 400

    if find_user(username):
        return jsonify(success=False, message="User already exists"), 400

    if country == "Rwandans" and (not national_id or not province):
        return jsonify(success=False, message="Fill National ID and Province"), 400
    if country == "Outsider" and (not passport_no or not country_name):
        return jsonify(success=False, message="Fill Passport Number and Country Name"), 400

    user = {
        "id": str(uuid.uuid4()),
        "username": username,
        "name": name,
        "email": email,
        "password": generate_password_hash(password),
        "country": country,
        "national_id": national_id,
        "province": province,
        "passport_no": passport_no,
        "country_name": country_name,
        "dob": dob,
        "phone": phone,
        "bio": "",
        "profile_pic": None,
        "created_at": datetime.utcnow().isoformat()
    }

    data_store["users"].append(user)
    save_data()

    return jsonify(success=True, message="User registered successfully!")


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").lower().strip()
    password = data.get("password", "")

    user = find_user(username)
    if user and check_password_hash(user["password"], password):
        session["username"] = username
        return jsonify(success=True, message="Login successful")
    else:
        return jsonify(success=False, message="Invalid username or password"), 401

@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("login_page"))

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/dashboard")
@login_required
def dashboard():
    data_store = load_data()
    user = next((u for u in data_store["users"] if u["username"] == session["username"]), None)
    for post in data_store.get("posts", []):
        post.setdefault("liked_by", [])
        post.setdefault("comments", [])
        post.setdefault("media", [])
    for story in data_store.get("stories", []):
        story.setdefault("liked_by", [])
        story.setdefault("comments", [])
        story.setdefault("media", [])
    notifications = [n for n in data_store.get("notifications", []) if n.get("user") == user["username"]]
    return render_template(
        "dashboard.html",
        user=user,
        users=data_store.get("users", []),
        posts=data_store.get("posts", []),
        stories=data_store.get("stories", []),
        ads=data_store.get("ads", []),
        notifications=notifications
    )

def save_uploaded_files(files):
    urls = []
    for f in files:
        if not f or f.filename == '':
            continue
        filename = secure_filename(f.filename)
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        f.save(filepath)
        urls.append(url_for('uploaded_file', filename=unique_name))
    return urls

# --- APIs ---

@app.route("/api/posts", methods=["GET", "POST"])
@login_required
def api_posts():
    data_store = load_data()
    user = next((u for u in data_store["users"] if u["username"] == session["username"]), None)
    if request.method == "GET":
        return jsonify(data_store.get("posts", []))

    content = request.form.get("content", "").strip()
    if not content:
        return jsonify({"error": "Content is required"}), 400

    media_urls = save_uploaded_files(request.files.getlist("media"))

    post = {
        "id": str(uuid.uuid4()),
        "username": user["username"],
        "content": content,
        "media": media_urls,
        "liked_by": [],
        "comments": [],
        "created_at": datetime.utcnow().isoformat()
    }
    data_store.setdefault("posts", []).insert(0, post)
    save_data()
    return jsonify(post), 201

@app.route("/api/stories", methods=["GET", "POST"])
@login_required
def api_stories():
    user = find_user(session["username"])
    if request.method == "GET":
        return jsonify(data_store.get("stories", []))

    content = request.form.get("content", "").strip()
    if not content:
        return jsonify({"error": "Content is required"}), 400

    media_urls = save_uploaded_files(request.files.getlist("media"))

    story = {
        "id": str(uuid.uuid4()),
        "username": user["username"],
        "content": content,
        "media": media_urls,
        "liked_by": [],
        "comments": [],
        "created_at": datetime.utcnow().isoformat()
    }
    data_store.setdefault("stories", []).insert(0, story)
    save_data()
    return jsonify(story), 201

@app.route("/api/ads", methods=["GET", "POST"])
@login_required
def api_ads():
    user = find_user(session["username"])
    if request.method == "GET":
        return jsonify(data_store.get("ads", []))

    content = request.form.get("content", "").strip()
    payment_method = request.form.get("payment")
    if not content or not payment_method:
        return jsonify({"error": "Content and payment method are required"}), 400

    media_urls = save_uploaded_files(request.files.getlist("media"))

    ad = {
        "id": str(uuid.uuid4()),
        "username": user["username"],
        "content": content,
        "payment_method": payment_method,
        "media": media_urls,
        "created_at": datetime.utcnow().isoformat()
    }
    data_store.setdefault("ads", []).insert(0, ad)
    data_store.setdefault("notifications", []).append({
        "id": str(uuid.uuid4()),
        "user": user["username"],
        "text": f"Your ad was posted (payment: {payment_method})",
        "read": False,
        "created_at": datetime.utcnow().isoformat()
    })
    save_data()
    return jsonify(ad), 201

@app.route("/api/messages/start", methods=["POST"])
@login_required
def api_messages_start():
    user = find_user(session["username"])
    data = request.get_json() or {}
    with_username = data.get("with")
    if not with_username or not find_user(with_username):
        return jsonify({"error": "User not found"}), 404
    # Check if any message exists between users
    msgs = [m for m in data_store.get("messages", []) if
            (m["sender"] == user["username"] and m["receiver"] == with_username) or
            (m["receiver"] == user["username"] and m["sender"] == with_username)]
    if not msgs:
        # Optionally create a placeholder message or just return success
        # Here, just return success (frontend will open chat window)
        return jsonify({"success": True, "started": True}), 200
    return jsonify({"success": True, "started": False}), 200

@app.route("/api/messages/", methods=["GET", "POST"])
@login_required
def api_messages():
    user = find_user(session["username"])

    if request.method == "GET":
        with_user = request.args.get("with")
        if with_user:
            msgs = [m.copy() for m in data_store.get("messages", []) if
                    (m["sender"] == user["username"] and m["receiver"] == with_user) or
                    (m["receiver"] == user["username"] and m["sender"] == with_user)]
            msgs_sorted = sorted(msgs, key=lambda x: x.get("created_at", ""))
            # Convert media list to string for frontend compatibility
            for msg in msgs_sorted:
                media = msg.get("media", None)
                if isinstance(media, list):
                    if len(media) == 1:
                        msg["media"] = media[0]
                    elif len(media) == 0:
                        msg["media"] = None
            return jsonify(msgs_sorted)
        else:
            msgs = [m for m in data_store.get("messages", []) if m["sender"] == user["username"] or m["receiver"] == user["username"]]
            partners = []
            seen = set()
            for m in sorted(msgs, key=lambda x: x.get("created_at", ""), reverse=True):
                partner = m["receiver"] if m["sender"] == user["username"] else m["sender"]
                if partner not in seen:
                    seen.add(partner)
                    partners.append({"username": partner})
            return jsonify(partners)

    receiver = request.form.get("receiver")
    text = request.form.get("text", "").strip()
    if not receiver or (not text and not request.files.getlist("media")):
        return jsonify({"error": "Receiver and message content/media required"}), 400

    if not find_user(receiver):
        return jsonify({"error": "Receiver user not found"}), 404

    media_urls = save_uploaded_files(request.files.getlist("media"))

    message = {
        "id": str(uuid.uuid4()),
        "sender": user["username"],
        "receiver": receiver,
        "text": text,
        "media": media_urls,
        "created_at": datetime.utcnow().isoformat()
    }
    data_store.setdefault("messages", []).append(message)

    data_store.setdefault("notifications", []).append({
        "id": str(uuid.uuid4()),
        "user": receiver,
        "text": f"New message from {user['username']}",
        "read": False,
        "created_at": datetime.utcnow().isoformat()
    })

    save_data()
    return jsonify(message), 201

@app.route("/api/notifications", methods=["GET"])
@login_required
def api_notifications():
    data_store = load_data()
    user = next((u for u in data_store["users"] if u["username"] == session["username"]), None)
    notifs = [n for n in data_store.get("notifications", []) if n.get("user") == user["username"]]
    notifs_sorted = sorted(notifs, key=lambda x: x.get("created_at", ""), reverse=True)
    return jsonify(notifs_sorted)

@app.route("/api/notifications/read/<notif_id>", methods=["POST"])
@login_required
def api_notifications_read(notif_id):
    user = find_user(session["username"])
    for n in data_store.get("notifications", []):
        if n.get("id") == notif_id and n.get("user") == user["username"]:
            n["read"] = True
            save_data()
            return jsonify({"success": True})
    return jsonify({"error": "Notification not found"}), 404

@app.route("/api/like", methods=["POST"])
@login_required
def api_like():
    user = find_user(session["username"])
    data = request.get_json() or {}
    item_type = data.get("type")  # "post" or "story"
    item_id = data.get("id")
    if item_type not in ("post", "story") or not item_id:
        return jsonify({"error": "Invalid data"}), 400

    target_list = data_store.get("posts") if item_type == "post" else data_store.get("stories")
    item = next((i for i in target_list if i["id"] == item_id), None)
    if not item:
        return jsonify({"error": f"{item_type} not found"}), 404

    if user["username"] in item["liked_by"]:
        item["liked_by"].remove(user["username"])
        action = "unliked"
    else:
        item["liked_by"].append(user["username"])
        action = "liked"
        owner = item.get("username")
        if owner and owner != user["username"]:
            data_store.setdefault("notifications", []).append({
                "id": str(uuid.uuid4()),
                "user": owner,
                "text": f"{user['username']} liked your {item_type}",
                "read": False,
                "created_at": datetime.utcnow().isoformat()
            })

    save_data()
    return jsonify({"liked_by": item["liked_by"], "action": action})

@app.route("/api/comment", methods=["POST"])
@login_required
def api_comment():
    data_store = load_data()
    user = next((u for u in data_store["users"] if u["username"] == session["username"]), None)
    data = request.get_json() or {}
    item_type = data.get("type")  # "post" or "story"
    item_id = data.get("id")
    comment_text = data.get("comment", "").strip()
    if item_type not in ("post", "story") or not item_id or not comment_text:
        return jsonify({"error": "Invalid data"}), 400

    target_list = data_store.get("posts") if item_type == "post" else data_store.get("stories")
    item = next((i for i in target_list if i["id"] == item_id), None)
    if not item:
        return jsonify({"error": f"{item_type} not found"}), 404

    comment = {
        "id": str(uuid.uuid4()),
        "username": user["username"],
        "text": comment_text,
        "created_at": datetime.utcnow().isoformat()
    }
    item.setdefault("comments", []).append(comment)

    owner = item.get("username")
    if owner and owner != user["username"]:
        data_store.setdefault("notifications", []).append({
            "id": str(uuid.uuid4()),
            "user": owner,
            "text": f"{user['username']} commented on your {item_type}",
            "read": False,
            "created_at": datetime.utcnow().isoformat()
        })

    save_data()
    return jsonify(comment)

@app.route("/api/search")
@login_required
def api_search():
    query = (request.args.get("q") or "").lower()
    if not query:
        return jsonify({"error": "Query parameter required"}), 400
    posts = [p for p in data_store.get("posts", []) if query in p.get("content", "").lower()]
    stories = [s for s in data_store.get("stories", []) if query in s.get("content", "").lower()]
    ads = [a for a in data_store.get("ads", []) if query in a.get("content", "").lower()]
    users = [u for u in data_store.get("users", []) if query in u.get("username", "").lower() or query in u.get("name", "").lower()]
    return jsonify({
        "posts": posts,
        "stories": stories,
        "ads": ads,
        "users": [{"username": u["username"], "name": u["name"]} for u in users]
    })

@app.route("/api/profile/edit", methods=["POST"])
@login_required
def api_profile_edit():
    user = find_user(session["username"])
    name = request.form.get("name", "").strip()
    bio = request.form.get("bio", "").strip()
    phone = request.form.get("phone", "").strip()

    file = request.files.get("profile_pic")
    if file and file.filename != "":
        filename = secure_filename(file.filename)
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        file.save(filepath)
        user["profile_pic"] = url_for('uploaded_file', filename=unique_name)

    if name:
        user["name"] = name
    if bio:
        user["bio"] = bio
    if phone:
        user["phone"] = phone

    save_data()
    return jsonify(success=True, message="Profile updated", user=user)
@app.route("/api/profile")
@login_required
def api_profile():
    user = find_user(session["username"])
    if not user:
        return jsonify({"error": "User not found"}), 404
    # Remove password from response for security
    user_copy = user.copy()
    user_copy.pop("password", None)
    return jsonify(user_copy)


if __name__ == "__main__":
    app.run(debug=True, port=2080)
