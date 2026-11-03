import sqlite3
from src.ingestion import migrations as mig
from src.security import auth, workspaces


def _db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "t.db"))
    mig.migrate(conn)
    return conn


def test_password_hash_and_verify(tmp_path):
    conn = _db(tmp_path)
    uid = auth.create_user(conn, "a@example.com", "password-123456", "Alice")
    row = conn.execute("SELECT password_hash FROM users WHERE user_id=?", (uid,)).fetchone()
    assert auth.verify_password("password-123456", row[0])
    assert not auth.verify_password("wrong", row[0])
    conn.close()


def test_session_create_resolve_revoke(tmp_path):
    conn = _db(tmp_path)
    uid = auth.create_user(conn, "b@example.com", "password-123456")
    token = auth.create_session(conn, uid)
    assert auth.resolve_session(conn, token) == uid
    auth.revoke_session(conn, token)
    assert auth.resolve_session(conn, token) is None
    conn.close()


def test_workspace_membership_and_collection(tmp_path):
    conn = _db(tmp_path)
    uid = auth.create_user(conn, "c@example.com", "password-123456")
    ws = workspaces.create_workspace(conn, "ws", "ws", uid)
    workspaces.add_member(conn, ws, uid, "owner", uid)
    assert workspaces.get_membership(conn, uid, ws) == "owner"
    cid = workspaces.create_collection(conn, ws, "col", "", "private", uid)
    assert cid.startswith("col-")
    conn.close()
