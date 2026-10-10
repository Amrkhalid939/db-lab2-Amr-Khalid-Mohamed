"""Automated tests: run against a real MySQL database built from database/schema.sql.
Run:  python -m pytest -q      (they empty the tables first; use a test database!)"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app, query  # noqa: E402


@pytest.fixture
def client():
    app.config["TESTING"] = True
    query("DELETE FROM todos")
    query("DELETE FROM users")
    with app.test_client() as c:
        yield c


def register(c, name="Sara", email="sara@mail.com", pw="secret", confirm=None):
    return c.post("/register", data={"name": name, "email": email, "password": pw,
                                     "confirm_password": pw if confirm is None else confirm})


def login(c, email="sara@mail.com", pw="secret"):
    return c.post("/login", data={"email": email, "password": pw})


def test_list_requires_login(client):
    r = client.get("/todos")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")


def test_register_empty_form_messages(client):
    r = register(client, name="  ", email="", pw="", confirm="")
    body = r.get_data(as_text=True)
    for msg in ["Name is required", "Email is required", "Password is required",
                "Confirm password is required"]:
        assert msg in body
    assert query("SELECT COUNT(*) n FROM users", fetch="one")["n"] == 0


def test_passwords_do_not_match(client):
    assert "Passwords do not match" in register(client, confirm="other").get_data(as_text=True)


def test_register_logs_in_and_hashes(client):
    r = register(client)
    assert r.headers["Location"].endswith("/todos")
    h = query("SELECT password_hash FROM users", fetch="one")["password_hash"]
    assert h.startswith("$2b$12$") and "secret" not in h


def test_duplicate_email(client):
    register(client)
    client.post("/logout")
    assert "Email Already Exists" in register(client, name="Again").get_data(as_text=True)


def test_same_login_error(client):
    register(client)
    client.post("/logout")
    a = login(client, pw="wrong").get_data(as_text=True)
    b = login(client, email="nobody@mail.com").get_data(as_text=True)
    assert "Invalid email or password" in a and "Invalid email or password" in b


def test_sql_injection_login(client):
    register(client)
    client.post("/logout")
    r = login(client, email="' OR '1'='1' -- ", pw="x")
    assert "Invalid email or password" in r.get_data(as_text=True)


def test_todo_crud_and_validation(client):
    register(client)
    assert "Your list is empty" in client.get("/todos").get_data(as_text=True)
    assert "Title is required" in client.post("/todos/add", data={"title": "   "}).get_data(as_text=True)
    assert "Title is too long" in client.post("/todos/add", data={"title": "x" * 201}).get_data(as_text=True)
    client.post("/todos/add", data={"title": "Buy oat milk"})
    client.post("/todos/add", data={"title": "Finish the lab"})
    body = client.get("/todos").get_data(as_text=True)
    assert body.index("Finish the lab") < body.index("Buy oat milk")  # newest first
    tid = query("SELECT todo_id FROM todos WHERE title='Buy oat milk'", fetch="one")["todo_id"]
    client.post(f"/todos/{tid}/edit", data={"title": "Buy almond milk"})
    client.post(f"/todos/{tid}/done", data={"is_done": "1"})
    row = query("SELECT title, is_done FROM todos WHERE todo_id=%s", (tid,), fetch="one")
    assert row == {"title": "Buy almond milk", "is_done": 1}
    client.post(f"/todos/{tid}/delete")
    assert query("SELECT COUNT(*) n FROM todos", fetch="one")["n"] == 1


def test_users_cannot_touch_each_others_todos(client):
    register(client)
    client.post("/todos/add", data={"title": "Sara's secret"})
    tid = query("SELECT todo_id FROM todos", fetch="one")["todo_id"]
    client.post("/logout")
    register(client, name="Omar", email="omar@mail.com")
    assert "Sara&#39;s secret" not in client.get("/todos").get_data(as_text=True)
    client.post(f"/todos/{tid}/edit", data={"title": "hacked"})
    client.post(f"/todos/{tid}/done", data={"is_done": "1"})
    client.post(f"/todos/{tid}/delete")
    row = query("SELECT title, is_done FROM todos WHERE todo_id=%s", (tid,), fetch="one")
    assert row == {"title": "Sara's secret", "is_done": 0}


def test_foreign_key_rejects_unknown_user(client):
    import pymysql
    with pytest.raises(pymysql.err.IntegrityError) as e:
        query("INSERT INTO todos (user_id, title) VALUES (%s, %s)", (999999, "orphan"))
    assert e.value.args[0] == 1452
