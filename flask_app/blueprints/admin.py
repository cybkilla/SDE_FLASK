# flask_app/blueprints/admin.py — Dashboard admin pertinence des conseils

import os
from flask import Blueprint, render_template, jsonify, request, abort
from flask_login import current_user, login_required

bp = Blueprint("admin", __name__, url_prefix="/admin")

_ADMIN_EMAILS = [e.strip() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]


def _require_admin():
    if not current_user.is_authenticated:
        abort(403)
    if _ADMIN_EMAILS and current_user.email not in _ADMIN_EMAILS:
        abort(403)


@bp.route("/")
@login_required
def dashboard():
    _require_admin()
    return render_template("admin.html")


@bp.route("/advisor-config", methods=["GET"])
@login_required
def get_advisor_config():
    _require_admin()
    from portfolio.config_advisor import get_config, DEFAULTS
    cfg = get_config(current_user.id)
    return jsonify({"ok": True, "config": cfg, "defaults": DEFAULTS})


@bp.route("/advisor-config", methods=["POST"])
@login_required
def save_advisor_config():
    _require_admin()
    data = request.get_json(silent=True) or {}
    try:
        from portfolio.config_advisor import save_config, reset_config
        if data.get("reset"):
            reset_config(current_user.id)
            from portfolio.config_advisor import DEFAULTS
            return jsonify({"ok": True, "config": DEFAULTS})
        cfg = save_config(current_user.id, data)
        return jsonify({"ok": True, "config": cfg})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/stats")
@login_required
def stats():
    _require_admin()
    try:
        from portfolio.evaluator import evaluate_pending, get_global_stats
        eval_result = evaluate_pending(days_back=90)
        global_stats = get_global_stats()
        return jsonify({"ok": True, "eval": eval_result, "stats": global_stats})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500
