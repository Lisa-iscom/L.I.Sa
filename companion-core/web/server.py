"""
web/server.py — Flask web server.

Routes:
  GET  /           → chat UI
  POST /login      → password authentication
  GET  /logout     → clear session
  POST /chat       → SSE streaming (web UI)
  POST /api/chat   → JSON API (X-Password header)
  GET  /health     → health check
"""

import logging
import os
import sys

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    stream_with_context,
    url_for,
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logger = logging.getLogger(__name__)


def create_app(config: dict, brain) -> Flask:

    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    app = Flask(__name__, template_folder=template_dir)

    app.secret_key = config["web"].get("session_secret", "dev-secret-change-me")
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    password = config["web"]["password"]

    def is_logged_in() -> bool:
        return session.get("authenticated") is True

    def check_api_auth() -> bool:
        return (
            request.headers.get("X-Password") == password
            or request.args.get("password") == password
        )

    @app.route("/")
    def index():
        if not is_logged_in():
            return redirect(url_for("login_page"))
        return render_template("chat.html")

    @app.route("/login", methods=["GET"])
    def login_page():
        if is_logged_in():
            return redirect(url_for("index"))
        return render_template("chat.html", login_mode=True)

    @app.route("/login", methods=["POST"])
    def login():
        data = request.get_json(silent=True) or {}
        if data.get("password") == password:
            session["authenticated"] = True
            session.permanent = True
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "Wrong password"}), 401

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login_page"))

    @app.route("/chat", methods=["POST"])
    def chat():
        if not is_logged_in():
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json(silent=True) or {}
        user_message = (data.get("message") or "").strip()
        if not user_message:
            return jsonify({"error": "Empty message"}), 400

        def generate():
            try:
                for chunk in brain.stream_response(user_message):
                    safe = chunk.replace("\n", "\\n")
                    yield f"data: {safe}\n\n"
            except Exception as e:
                logger.error("Stream error: %s", e)
                yield "data: ⚠️ Server error\n\n"
            finally:
                yield "data: [DONE]\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        if not check_api_auth():
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

        data = request.get_json(silent=True) or {}
        user_message = (data.get("message") or "").strip()
        if not user_message:
            return jsonify({"ok": False, "error": "Empty message"}), 400

        try:
            reply = "".join(brain.stream_response(user_message))
        except Exception as e:
            logger.error("API chat error: %s", e)
            return jsonify({"ok": False, "error": str(e)}), 500

        return jsonify({"ok": True, "reply": reply})

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    return app
