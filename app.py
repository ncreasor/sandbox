import os, hmac, hashlib, json, datetime
from openai import AsyncOpenAI
from dotenv import load_dotenv
from quart import Quart, request, jsonify, render_template
from logic.core import processing
from logic.ofd import check
from panel.site_routes import site_routes
from logic.cache import get_pyrus_key, get_cache_config
from init_db import init_db
from logic.regform_updater import scheduler, form_register, requests_today
#init_db()
app = Quart(__name__)
app.secret_key = os.urandom(24)

sessions = {}
answer = {}
load_dotenv()

# Assistants для каждого tenant (создаются при первом обращении)
tenant_assistants = {}  # {tenant_id: {"main": asst_id, "integrations": asst_id}}
assistants_lock = None


def sign(message, secret, signature):
    if not signature:
        return False
    digest = hmac.new(secret, msg=message, digestmod=hashlib.sha1).hexdigest()
    return hmac.compare_digest(digest, signature.lower())

@app.before_serving
async def startup():
    global assistants_lock
    import asyncio
    assistants_lock = asyncio.Lock()
    scheduler.start()
    await form_register()

@app.after_serving
async def shutdown():
    from logic.regform_updater import dump_stats
    await dump_stats()

@app.route("/webhook/<tenant_id>", methods=["POST"])
async def webhook(tenant_id):
    pyrus_key, model = get_pyrus_key(tenant_id)
    if not pyrus_key:
        return jsonify({"error": "Unknown tenant"}), 404
    config = get_cache_config(pyrus_key)
    secret = pyrus_key.encode()
    signature = request.headers.get("x-pyrus-sig")

    if not sign(body := await request.data, secret, signature):
        return jsonify({"error": "Invalid signature"}), 400
    
    requests_today[tenant_id] = requests_today.get(tenant_id, 0) + 1

    task = json.loads(body.decode())["task"]
    id = task["id"]

    if config["ofd"]["enabled"]:
        ofd_day = config["ofd"]["day"]
        if ofd_day and datetime.datetime.today().day == ofd_day and id not in answer:
            return await check(task, id, sessions, answer, pyrus_key, tenant_id)
        
    client = AsyncOpenAI(api_key=config["api_keys"]["openai_api_key"])
    return await processing(task, id, sessions, pyrus_key, model, client, tenant_id)

app.register_blueprint(site_routes)

@app.errorhandler(404)
async def not_found(e):
    return await render_template("404.html"), 404

@app.errorhandler(405)
async def method_not_allowed(e):
    return await render_template("405.html"), 405

@app.errorhandler(500)
async def internal_server_error(e):
    return await render_template("500.html"), 500

@app.errorhandler(502)
async def bad_gateway(e):
    return await render_template("502.html"), 502

@app.errorhandler(503)
async def service_unavailable(e):
    return await render_template("503.html"), 503



if __name__ == "__main__":
    app.run(debug=True)
