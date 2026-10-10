"""DB Lab 2 - Login & To-Do application (Flask + PyMySQL + bcrypt)."""
import os
from functools import wraps

import bcrypt
import pymysql
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

TITLE_MAX = 200


# ---------------------------------------------------------------- database
def get_db():
    """Open a new connection. Every value is sent as a %s parameter."""
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 3306)),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ.get("DB_NAME", "registration"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def query(sql, params=(), fetch=None):
    """Run one parameterised statement. fetch: None, 'one' or 'all'."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
            return cur.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------- helpers
def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def validate_title(title):
    if not title.strip():
        return "Title is required"
    if len(title.strip()) > TITLE_MAX:
        return "Title is too long"
    return None


# ---------------------------------------------------------------- auth
@app.route("/")
def index():
    return redirect(url_for("todos" if "user_id" in session else "login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("todos"))
    form = {"name": "", "email": ""}
    errors = {}
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        form = {"name": name, "email": email}

        if not name:
            errors["name"] = "Name is required"
        if not email:
            errors["email"] = "Email is required"
        if not password:
            errors["password"] = "Password is required"
        if not confirm:
            errors["confirm_password"] = "Confirm password is required"
        elif password and password != confirm:
            errors["confirm_password"] = "Passwords do not match"

        if not errors:
            pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()
            try:
                query("INSERT INTO users (email, name, password_hash) VALUES (%s, %s, %s)",
                      (email, name, pw_hash))
            except pymysql.err.IntegrityError as e:
                if e.args[0] == 1062:  # duplicate key -> UNIQUE(email)
                    errors["email"] = "Email Already Exists"
                else:
                    raise
            else:
                user = query("SELECT user_id, name, password_hash FROM users WHERE email = %s",
                             (email,), fetch="one")
                session.clear()
                session["user_id"] = user["user_id"]
                session["name"] = user["name"]
                return redirect(url_for("todos"))
    return render_template("register.html", form=form, errors=errors), (400 if errors else 200)


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("todos"))
    email = ""
    errors = {}
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email:
            errors["email"] = "Email is required"
        if not password:
            errors["password"] = "Password is required"
        if not errors:
            user = query("SELECT user_id, name, password_hash FROM users WHERE email = %s",
                         (email,), fetch="one")
            if user and bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
                session.clear()
                session["user_id"] = user["user_id"]
                session["name"] = user["name"]
                return redirect(url_for("todos"))
            errors["form"] = "Invalid email or password"
    return render_template("login.html", email=email, errors=errors), (400 if errors else 200)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- to-dos
def render_list(errors=None, new_title="", edit_values=None, status=200):
    items = query("SELECT todo_id, title, is_done, created_at FROM todos "
                  "WHERE user_id = %s ORDER BY todo_id DESC",
                  (session["user_id"],), fetch="all")
    show = request.args.get("show", "all")
    open_count = sum(1 for t in items if not t["is_done"])
    if show == "open":
        visible = [t for t in items if not t["is_done"]]
    elif show == "done":
        visible = [t for t in items if t["is_done"]]
    else:
        show, visible = "all", items
    return render_template("todos.html", todos=visible, total=len(items), open_count=open_count,
                           show=show, errors=errors or {}, new_title=new_title,
                           edit_values=edit_values or {}), status


def back_to_list():
    show = request.args.get("show")
    return redirect(url_for("todos", show=show) if show in ("open", "done") else url_for("todos"))


@app.route("/todos")
@login_required
def todos():
    return render_list()


@app.route("/todos/add", methods=["POST"])
@login_required
def add_todo():
    title = request.form.get("title", "")
    error = validate_title(title)
    if error:
        return render_list(errors={"new": error}, new_title=title, status=400)
    query("INSERT INTO todos (user_id, title) VALUES (%s, %s)",
          (session["user_id"], title.strip()))
    return back_to_list()


@app.route("/todos/<int:todo_id>/edit", methods=["POST"])
@login_required
def edit_todo(todo_id):
    title = request.form.get("title", "")
    error = validate_title(title)
    if error:
        return render_list(errors={todo_id: error}, edit_values={todo_id: title}, status=400)
    query("UPDATE todos SET title = %s WHERE todo_id = %s AND user_id = %s",
          (title.strip(), todo_id, session["user_id"]))
    return back_to_list()


@app.route("/todos/<int:todo_id>/done", methods=["POST"])
@login_required
def toggle_todo(todo_id):
    is_done = 1 if request.form.get("is_done") == "1" else 0
    query("UPDATE todos SET is_done = %s WHERE todo_id = %s AND user_id = %s",
          (is_done, todo_id, session["user_id"]))
    return back_to_list()


@app.route("/todos/<int:todo_id>/delete", methods=["POST"])
@login_required
def delete_todo(todo_id):
    query("DELETE FROM todos WHERE todo_id = %s AND user_id = %s",
          (todo_id, session["user_id"]))
    return back_to_list()


# ---------------------------------------------------------------- errors
@app.errorhandler(404)
def not_found(_e):
    return render_template("error.html", title="Page not found",
                           message="The page you are looking for does not exist."), 404


@app.errorhandler(405)
def not_allowed(_e):
    return render_template("error.html", title="Not allowed",
                           message="That action is not allowed here."), 405


@app.errorhandler(Exception)
def server_error(e):
    if isinstance(e, HTTPException):
        return render_template("error.html", title=e.name, message=e.description), e.code
    app.logger.exception(e)
    return render_template("error.html", title="Something went wrong",
                           message="Please try again in a moment."), 500


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1",
            port=int(os.environ.get("PORT", 5000)))
