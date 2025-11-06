from quart import Blueprint, render_template, request, session, redirect
import bcrypt, json
from datetime import date
from dotenv import load_dotenv
from logic.serv import template
from logic.cache import get_mysql_connection, clear_cache, clear_all_cache

load_dotenv()
site_routes = Blueprint('site_routes', __name__)


# Хэширование пароля (при регистрации/добавлении пользователя)
def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    return hashed.decode()  # Сохраняем как строку в БД

# Проверка пароля
def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def check_tenant_credentials(tenant_id, login, password):
    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE tenant_id=%s AND login=%s", (tenant_id, login))
    row = c.fetchone()
    conn.close()
    return row is not None and check_password(password, row[0])

def check_admin_credentials(login, password):
    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("SELECT password FROM admins WHERE login=%s", (login,))
    row = c.fetchone()
    conn.close()
    return row is not None and check_password(password, row[0])

def get_all_users():
    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("""
        SELECT NULL as tenant_id, login, 'admin' as role FROM admins
        UNION ALL
        SELECT tenant_id, login, 'user' as role FROM users
    """)
    users = [{"tenant_id": row[0], "email": row[1], "role": row[2]} for row in c.fetchall()]
    conn.close()
    return users

def get_all_tenants():
    conn = get_mysql_connection()
    c = conn.cursor(dictionary=True)
    c.execute("""
        SELECT tenant_id, pyrus_key, gpt_model,
               allow_attachments_toggle, allow_multi_channel_toggle
        FROM tenants
    """)
    tenants = c.fetchall()
    conn.close()
    return tenants


def get_all_gpt_models():
    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("SELECT model_name FROM gpt_models")
    models = [row[0] for row in c.fetchall()]
    conn.close()
    return models

def get_all_api_keys():
    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("SELECT openai_api_key FROM api_keys LIMIT 1")
    row = c.fetchone()
    conn.close()
    return {
        "openai_api_key": row[0] if row else "",
    }

def get_all_stats():
    conn = get_mysql_connection()
    c = conn.cursor(dictionary=True)

    # Сумма всех запросов
    c.execute("SELECT SUM(request_count) AS total_requests FROM statistics")
    total_requests = c.fetchone()["total_requests"] or 1

    # Собираем статистику
    c.execute("""
        SELECT 
            t.tenant_id,
            s.date AS date,
            s.request_count AS request,
            s.task_count AS tasks,
            t.allow_attachments_toggle,
            t.allow_multi_channel_toggle,
            ROUND(COALESCE(s.request_count, 0) / %s * 100, 2) AS percentage
        FROM tenants t
        LEFT JOIN statistics s ON t.tenant_id = s.tenant_id
    """, (total_requests,))

    stats = []
    for row in c.fetchall():
        base = 130
        if row.get("allow_multi_channel_toggle"):
            base += 7
        if row.get("allow_attachments_toggle"):
            base += 25
        row["amount"] = f"${base}"

        # Расчёт запросов на задачу
        request = row.get("request", 0) or 0
        tasks = row.get("tasks", 0) or 1  # чтобы не делить на 0
        row["reqpertasks"] = round(request / tasks, 2) if tasks else "-"

        stats.append(row)

    conn.close()
    return stats



@site_routes.route("/", methods=["GET"])
async def login_page():
    return await render_template("index.html")

@site_routes.route("/login", methods=["POST"])
async def universal_login():
    data = await request.form
    login = data["login"]
    password = data["password"]
    tenant_id = data.get("tenant_id", "").strip()

    if tenant_id:
        if check_tenant_credentials(tenant_id, login, password):
            session["tenant"] = tenant_id
            session["login"] = login  # ← вот это добавь
            return redirect("/dashboard")
        return await render_template("index.html", error="Неверный логин или пароль")
    else:
        if check_admin_credentials(login, password):
            session["admin"] = login
            return redirect("/admin")

        return await render_template("index.html", error="Неверный логин или пароль")


@site_routes.route("/admin")
async def admin_panel():
    if "admin" not in session:
        return redirect("/")

    users = get_all_users()
    tenants = get_all_tenants()
    stats = get_all_stats()
    gpt_models = get_all_gpt_models()
    api_keys = get_all_api_keys()

    return await render_template(
        "admin.html",
        admin_login=session["admin"],
        users=users,
        tenants=tenants,
        stats=stats,
        gpt_models=gpt_models,
        api_keys=api_keys,
    )



@site_routes.route("/admin/api_keys", methods=["POST"])
async def update_api_keys():
    if "admin" not in session:
        return redirect("/")

    data = await request.form
    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO api_keys (id, openai_api_key)
        VALUES (1, %s)
        ON DUPLICATE KEY UPDATE
            openai_api_key = VALUES(openai_api_key)
    """, (data["openai_api_key"],))
    conn.commit()
    conn.close()
    return redirect("/admin")


@site_routes.route("/logout")
async def logout():
    session.clear()
    return await render_template("index.html")

@site_routes.route("/admin/create_user", methods=["POST"])
async def create_user():
    data = await request.form
    tenant_id = data.get("tenant_id")
    pyrus_key = data.get("pyrus_key")
    login = data.get("email")
    password = data.get("password")
    role = data.get("role")
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = get_mysql_connection()
    c = conn.cursor()

    if role == "admin":
        c.execute("SELECT 1 FROM admins WHERE login=%s", (login,))
        if c.fetchone():
            conn.close()
            return await render_template(
                "admin.html",
                error="Админ с таким логином уже существует",
                admin_login=session.get("admin"),
                users=get_all_users(),
                tenants=get_all_tenants(),
                gpt_models=get_all_gpt_models(),
                api_keys=get_all_api_keys(),
            )
        c.execute("INSERT INTO admins (login, password) VALUES (%s, %s)", (login, hashed))
    else:
        c.execute("SELECT 1 FROM tenants WHERE tenant_id=%s", (tenant_id,))
        if not c.fetchone():
            c.execute("INSERT INTO tenants (tenant_id, pyrus_key) VALUES (%s, %s)", (tenant_id, pyrus_key))

            # Добавляем начальную запись в statistics
            c.execute("""
                INSERT INTO statistics (tenant_id, date)
                VALUES (%s, %s)
            """, (tenant_id, date.today()))
    
        c.execute("SELECT 1 FROM users WHERE login=%s", (login,))
        if c.fetchone():
            conn.close()
            return await render_template(
                "admin.html",
                error="Пользователь с таким логином уже существует",
                admin_login=session.get("admin"),
                users=get_all_users(),
                tenants=get_all_tenants(),
                gpt_models=get_all_gpt_models(),
                api_keys=get_all_api_keys(),
            )

        c.execute("INSERT INTO users (tenant_id, login, password) VALUES (%s, %s, %s)", (tenant_id, login, hashed))

    conn.commit()
    clear_all_cache()
    conn.close()

    return await render_template(
        "admin.html",
        admin_login=session.get("admin"),
        users=get_all_users(),
        tenants=get_all_tenants(),
        gpt_models=get_all_gpt_models(),
        api_keys=get_all_api_keys(),
    )


@site_routes.route("/admin/edit_user/<string:login>", methods=["GET", "POST"])
async def edit_user(login):
    conn = get_mysql_connection()
    c = conn.cursor()

    if request.method == "POST":
        data = await request.form
        email = data["email"]
        password = data["password"]
        role = data["role"]
        tenant_id = data.get("tenant_id", "").strip()

        # Узнаем текущую роль
        c.execute("""
            SELECT 'admin' FROM admins WHERE login=%s
            UNION
            SELECT 'user' FROM users WHERE login=%s
        """, (login, login))
        current_role_row = c.fetchone()

        if not current_role_row:
            conn.close()
            return await render_template("admin.html", error="Пользователь не найден")

        current_role = current_role_row[0]

        # Валидация: если user без tenant_id
        if role == "user" and not tenant_id:
            conn.close()
            return await render_template("edit_user.html", user={"email": email, "role": role, "tenant_id": tenant_id},
                                         error="У пользователей должен быть указан эндпоинт")

        # Меняем роль: удаляем из старой таблицы
        if current_role != role:
            if current_role == "admin":
                c.execute("DELETE FROM admins WHERE login=%s", (login,))
            else:
                c.execute("DELETE FROM users WHERE login=%s", (login,))

        # Хеш пароля, если указан
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode() if password else None

        if role == "admin":
            if hashed:
                c.execute("REPLACE INTO admins (login, password) VALUES (%s, %s)", (email, hashed))
            else:
                c.execute("REPLACE INTO admins (login) VALUES (%s)", (email,))
        else:
            if hashed:
                c.execute("REPLACE INTO users (login, password, tenant_id) VALUES (%s, %s, %s)", (email, hashed, tenant_id))
            else:
                c.execute("REPLACE INTO users (login, tenant_id) VALUES (%s, %s)", (email, tenant_id))

        conn.commit()
        clear_all_cache()
        conn.close()
        return redirect("/admin")

    # GET-запрос
    c.execute("""
        SELECT login, 'admin', NULL FROM admins WHERE login=%s
        UNION
        SELECT login, 'user', tenant_id FROM users WHERE login=%s
    """, (login, login))
    row = c.fetchone()
    conn.close()

    if not row:
        return await render_template("admin.html", error="Пользователь не найден")

    user = {"email": row[0], "role": row[1], "tenant_id": row[2]}
    return await render_template("edit_user.html", user=user)




@site_routes.route("/admin/delete_user/<string:login>")
async def delete_user(login):
    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE login=%s", (login,))
    c.execute("DELETE FROM users WHERE login=%s", (login,))
    conn.commit()
    clear_all_cache()
    conn.close()
    return redirect("/admin")

@site_routes.route("/admin/delete_tenant/<string:tenant_id>")
async def delete_tenant(tenant_id):
    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("DELETE FROM statistics WHERE tenant_id=%s", (tenant_id,))
    c.execute("DELETE FROM users WHERE tenant_id=%s", (tenant_id,))
    c.execute("DELETE FROM tenants WHERE tenant_id=%s", (tenant_id,))

    conn.commit()
    clear_all_cache()
    conn.close()
    return redirect("/admin")


@site_routes.route("/admin/edit_tenant/<string:tenant_id>", methods=["GET", "POST"])
async def edit_tenant(tenant_id):
    conn = get_mysql_connection()
    c = conn.cursor()
    if request.method == "POST":
        data = await request.form
        new_tenant_id = data["tenant_id"]
        pyrus_key = data["pyrus_key"]
        gpt_model = data["gpt_model"]
        attachments_toggle_allowed = "attachments_toggle_allowed" in data
        multi_channel_toggle_allowed = "multi_channel_toggle_allowed" in data

        c.execute("""
            UPDATE tenants SET tenant_id=%s, pyrus_key=%s, gpt_model=%s,
            allow_attachments_toggle=%s, allow_multi_channel_toggle=%s
            WHERE tenant_id=%s
        """, (new_tenant_id, pyrus_key, gpt_model,
            attachments_toggle_allowed, multi_channel_toggle_allowed,
            tenant_id))
        conn.commit()
        clear_cache(pyrus_key)
        conn.close()
        return redirect("/admin")

    c.execute("SELECT tenant_id, pyrus_key, gpt_model, allow_attachments_toggle, allow_multi_channel_toggle FROM tenants WHERE tenant_id=%s", (tenant_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return await render_template("admin.html", error="Организация не найдена")

    tenant = {
        "tenant_id": row[0],
        "pyrus_key": row[1],
        "gpt_model": row[2],
        "attachments_toggle_allowed": row[3],
        "multi_channel_toggle_allowed": row[4],
    }
    gpt_models = get_all_gpt_models()
    return await render_template("edit_tenant.html", tenant=tenant, gpt_models=gpt_models)

@site_routes.route("/admin/model", methods=["POST"])
async def add_model():
    data = await request.form
    model_name = data.get("gpt_model_name")
    if model_name:
        conn = get_mysql_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT IGNORE INTO gpt_models (model_name) VALUES (%s)", (model_name,))
            conn.commit()
            clear_all_cache()
        finally:
            conn.close()
    return redirect("/admin")

@site_routes.route("/admin/delete_model/<string:model_name>")
async def delete_model(model_name):
    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("DELETE FROM gpt_models WHERE model_name = %s", (model_name,))
    conn.commit()
    clear_all_cache()
    conn.close()
    return redirect("/admin")


@site_routes.route("/dashboard")
async def dashboard():
    if "tenant" not in session:
        return redirect("/")

    tenant_id = session["tenant"]
    login = session["login"]

    conn = get_mysql_connection()
    c = conn.cursor()

    c.execute("SELECT pyrus_key, allow_attachments_toggle, allow_multi_channel_toggle FROM tenants WHERE tenant_id=%s", (tenant_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return redirect("/")

    pyrus_key, allow_attachments_toggle, allow_multi_channel_toggle = row

    c.execute("SELECT ofd_day, ofd_template, ofd_enabled, ofd_greeting FROM ofd WHERE pyrus_key=%s", (pyrus_key,))
    row = c.fetchone()
    current_ofd_day, current_ofd_template, current_ofd_enabled, current_ofd_greeting = row or (None, "", False, "")

    c.execute("SELECT is_attachments_enabled, is_multi_channel_enabled, is_emergency_enabled, emergency_template FROM other WHERE pyrus_key=%s", (pyrus_key,))
    row = c.fetchone()
    current_attachments_enabled, current_multi_channel_enabled, current_emergency_message_enabled, current_emergency_message_text = row or (False, False, False, "")

    # Автосброс включённых значений, если фича запрещена
    if not allow_attachments_toggle and current_attachments_enabled:
        current_attachments_enabled = False
        c.execute("UPDATE other SET is_attachments_enabled=FALSE WHERE pyrus_key=%s", (pyrus_key,))
        conn.commit()

    if not allow_multi_channel_toggle and current_multi_channel_enabled:
        current_multi_channel_enabled = False
        c.execute("UPDATE other SET is_multi_channel_enabled=FALSE WHERE pyrus_key=%s", (pyrus_key,))
        conn.commit()

    c.execute("SELECT bot_login, temperature, stop_words, bot_stop_words, time_zone, work_from, work_to, work_from_weekend, work_to_weekend, offmsg FROM config WHERE pyrus_key=%s", (pyrus_key,))
    row = c.fetchone()
    if row:
        (current_bot_login, current_temperature, current_stop_words, current_bot_stop_words, current_timezone,
         current_work_from, current_work_to, current_work_from_weekend,
         current_work_to_weekend, current_offmsg) = row
        current_timezone = int(current_timezone)
        if not current_bot_stop_words:
            current_bot_stop_words = "Anydesk, .."
    else:
        current_bot_login = ""
        current_temperature = 0.5
        current_stop_words = ""
        current_bot_stop_words = "Anydesk, .."
        current_timezone = "UTC"
        current_work_from = current_work_to = current_work_from_weekend = current_work_to_weekend = current_offmsg = ""

    c.execute("""
        SELECT
            fc.form_enabled, fc.form_or_card, fc.form_template, fc.dynamic_fields,
            f.dictionary_id, f.dict_field_id,
            f.name_column, f.filter_column, f.filter_words
        FROM form_config fc
        LEFT JOIN form f ON fc.pyrus_key = f.pyrus_key
        WHERE fc.pyrus_key=%s
    """, (pyrus_key,))
    row = c.fetchone()
    if row:
        (current_form_enabled, current_form_or_card,  current_form_template, current_dynamic_fields,
         current_dictionary_id, current_dict_field_id,
         current_name_column, current_filter_column, current_filter_words) = row

        current_form_or_card = str(current_form_or_card or '')
        if current_form_or_card not in ('form', 'card'):
            current_form_or_card = ""
        if not current_form_template:
            current_form_template = template("logic/service.txt")
            c.execute("UPDATE form_config SET form_template=%s WHERE pyrus_key=%s", (current_form_template, pyrus_key))
            conn.commit()
            clear_cache(pyrus_key)
        if current_dynamic_fields:
            try:
                current_dynamic_fields = json.loads(current_dynamic_fields)
            except:
                current_dynamic_fields = []
        else:
            current_dynamic_fields = []
    else:
        current_form_enabled = False
        current_form_or_card = ""
        current_form_template = template("logic/service.txt")
        current_dictionary_id = current_dict_field_id = ""
        current_name_column = current_filter_column = current_filter_words = ""
        current_dynamic_fields = []

    c.execute("SELECT card_id, field_id, card_field_id, group_id FROM card WHERE pyrus_key=%s", (pyrus_key,))
    row = c.fetchone()
    current_card_id, current_field_id, current_card_field_id, current_group_id = row if row else ("", "", "", "")

    c.execute("SELECT template FROM template WHERE pyrus_key=%s", (pyrus_key,))
    row = c.fetchone()
    current_bot_template = row[0] if row and row[0] else "" #template("logic/template.txt")
    if not row or not row[0]:
        c.execute("INSERT INTO template (pyrus_key, template) VALUES (%s, %s) ON DUPLICATE KEY UPDATE template=%s", (pyrus_key, current_bot_template, current_bot_template))
        conn.commit()
        clear_cache(pyrus_key)

    conn.close()

    return await render_template(
        "dashboard.html",
        tenant_id=tenant_id,
        login=login,
        current_ofd_day=current_ofd_day,
        current_ofd_template=current_ofd_template,
        current_ofd_enabled=current_ofd_enabled,
        current_ofd_greeting=current_ofd_greeting,
        current_attachments_enabled=current_attachments_enabled,
        current_multi_channel_enabled=current_multi_channel_enabled,
        current_emergency_message_enabled=current_emergency_message_enabled,
        current_emergency_message_text=current_emergency_message_text,
        current_bot_login=current_bot_login,
        current_temperature=current_temperature,
        current_stop_words=current_stop_words,
        current_bot_stop_words=current_bot_stop_words,
        current_timezone=current_timezone,
        current_work_from=current_work_from,
        current_work_to=current_work_to,
        current_work_from_weekend=current_work_from_weekend,
        current_work_to_weekend=current_work_to_weekend,
        current_offmsg=current_offmsg,
        current_form_enabled=current_form_enabled,
        current_form_or_card=current_form_or_card,
        current_dictionary_id=current_dictionary_id,
        current_dict_field_id=current_dict_field_id,
        current_name_column=current_name_column,
        current_filter_column=current_filter_column,
        current_filter_words=current_filter_words,
        current_form_template=current_form_template,
        current_dynamic_fields=current_dynamic_fields,
        current_card_id=current_card_id,
        current_field_id=current_field_id,
        current_card_field_id=current_card_field_id,
        current_group_id=current_group_id,
        current_bot_template=current_bot_template,
        allow_attachments_toggle=allow_attachments_toggle,
        allow_multi_channel_toggle=allow_multi_channel_toggle
    )




@site_routes.route("/dashboard/form", methods=["POST"])
async def dashboard_form():
    if "tenant" not in session:
        return redirect("/")

    tenant_id = session["tenant"]
    form = await request.form

    dictionary_id = form.get("dictionary_id", "")
    dict_field_id = form.get("dict_field_id", "")
    name_column = form.get("name_column", "")
    filter_column = form.get("filter_column", "")
    filter_words = form.get("filter_words", "")

    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("SELECT pyrus_key FROM tenants WHERE tenant_id=%s", (tenant_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return redirect("/dashboard")

    pyrus_key = row[0]

    c.execute("SELECT 1 FROM form WHERE pyrus_key=%s", (pyrus_key,))
    if c.fetchone():
        c.execute("""
            UPDATE form SET
                dictionary_id=%s,
                dict_field_id=%s,
                name_column=%s,
                filter_column=%s,
                filter_words=%s
            WHERE pyrus_key=%s
        """, (dictionary_id, dict_field_id, name_column, filter_column, filter_words, pyrus_key))
    else:
        c.execute("""
            INSERT INTO form (
                pyrus_key, dictionary_id, dict_field_id, name_column, filter_column, filter_words
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (pyrus_key, dictionary_id, dict_field_id, name_column, filter_column, filter_words))
    conn.commit()
    clear_cache(pyrus_key)
    conn.close()

    return redirect("/dashboard")


@site_routes.route("/dashboard/form_config", methods=["POST"])
async def dashboard_form_config():
    if "tenant" not in session:
        return redirect("/")

    tenant_id = session["tenant"]
    form = await request.form

    form_enabled = form.get("form_enabled") == "on"
    form_or_card = form.get("form_or_card", "")
    form_template = form.get("form_template", "")
    dynamic_fields_raw = form.get("dynamic_fields", "[]")

    try:
        json.loads(dynamic_fields_raw)
    except:
        dynamic_fields_raw = "[]"

    conn = get_mysql_connection()
    c = conn.cursor()

    c.execute("SELECT pyrus_key FROM tenants WHERE tenant_id=%s", (tenant_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return redirect("/dashboard")

    pyrus_key = row[0]

    c.execute("SELECT 1 FROM form_config WHERE pyrus_key=%s", (pyrus_key,))
    if c.fetchone():
        c.execute("""
            UPDATE form_config SET
                form_enabled=%s,
                form_or_card=%s,
                form_template=%s,
                dynamic_fields=%s
            WHERE pyrus_key=%s
        """, (form_enabled, form_or_card, form_template, dynamic_fields_raw, pyrus_key))
    else:
        c.execute("""
            INSERT INTO form_config (
                pyrus_key, form_enabled, form_or_card, form_template, dynamic_fields
            ) VALUES (%s, %s, %s, %s, %s)
        """, (pyrus_key, form_enabled, form_or_card, form_template, dynamic_fields_raw))

    conn.commit()
    clear_cache(pyrus_key)
    conn.close()

    return redirect("/dashboard")





@site_routes.route("/dashboard/card", methods=["POST"])
async def dashboard_card():
    if "tenant" not in session:
        return redirect("/")

    tenant_id = session["tenant"]
    form = await request.form

    card_id = form.get("card_id", "")
    field_id = form.get("field_id", "")
    card_field_id = form.get("card_field_id", "")
    group_id = form.get("group_id", "")

    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("SELECT pyrus_key FROM tenants WHERE tenant_id=%s", (tenant_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return redirect("/dashboard")

    pyrus_key = row[0]

    c.execute("SELECT pyrus_key FROM card WHERE pyrus_key=%s", (pyrus_key,))
    exists = c.fetchone()

    if exists:
        c.execute("UPDATE card SET card_id=%s, field_id=%s, card_field_id=%s, group_id=%s WHERE pyrus_key=%s", (card_id, field_id, card_field_id, group_id, pyrus_key))
    else:
        c.execute("INSERT INTO card (pyrus_key, card_id, field_id, card_field_id, group_id) VALUES (%s, %s, %s, %s, %s)", (pyrus_key, card_id, field_id, card_field_id, group_id))


    conn.commit()
    clear_cache(pyrus_key)
    conn.close()

    return redirect("/dashboard")




@site_routes.route("/dashboard/ofd", methods=["POST"])
async def save_ofd():
    if "tenant" not in session:
        return redirect("/")

    data = await request.form
    ofd_day = int(data["ofd_day"])
    ofd_template = data["ofd_template"]
    ofd_enabled = "ofd_enabled" in data
    ofd_greeting = data.get("ofd_greeting", "Добрый день! Сегодня 28 число, день оплаты ОФД.")
    tenant_id = session["tenant"]

    conn = get_mysql_connection()
    c = conn.cursor()

    c.execute("SELECT pyrus_key FROM tenants WHERE tenant_id=%s", (tenant_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return redirect("/dashboard")

    pyrus_key = row[0]

    c.execute("SELECT 1 FROM ofd WHERE pyrus_key=%s", (pyrus_key,))
    if c.fetchone():
        c.execute(
            "UPDATE ofd SET ofd_day=%s, ofd_template=%s, ofd_enabled=%s, ofd_greeting=%s WHERE pyrus_key=%s",
            (ofd_day, ofd_template, ofd_enabled, ofd_greeting, pyrus_key)
        )
    else:
        c.execute(
            "INSERT INTO ofd (pyrus_key, ofd_day, ofd_template, ofd_enabled, ofd_greeting) VALUES (%s, %s, %s, %s, %s)",
            (pyrus_key, ofd_day, ofd_template, ofd_enabled, ofd_greeting)
        )

    conn.commit()
    clear_cache(pyrus_key)
    conn.close()

    return redirect("/dashboard")

@site_routes.route("/dashboard/other", methods=["POST"])
async def dashboard_other():
    if "tenant" not in session:
        return redirect("/")

    tenant_id = session["tenant"]
    form = await request.form
    attachments_enabled = form.get("attachments_enabled") == "on"
    multi_channel_enabled = form.get("multi_channel_enabled") == "on"
    emergency_enabled = form.get("emergency_message_enabled") == "on"
    emergency_text = form.get("emergency_message_text", "")

    conn = get_mysql_connection()
    c = conn.cursor()

    c.execute("SELECT pyrus_key, allow_attachments_toggle, allow_multi_channel_toggle FROM tenants WHERE tenant_id=%s", (tenant_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return redirect("/dashboard")

    pyrus_key, allow_attachments_toggle, allow_multi_channel_toggle = row

    # Принудительно сбросить, если запрет
    if not allow_attachments_toggle:
        attachments_enabled = False
    if not allow_multi_channel_toggle:
        multi_channel_enabled = False

    c.execute("SELECT pyrus_key FROM other WHERE pyrus_key=%s", (pyrus_key,))
    exists = c.fetchone()

    if exists:
        c.execute("""
            UPDATE other SET
                is_attachments_enabled=%s,
                is_multi_channel_enabled=%s,
                is_emergency_enabled=%s,
                emergency_template=%s
            WHERE pyrus_key=%s
        """, (attachments_enabled, multi_channel_enabled, emergency_enabled, emergency_text, pyrus_key))
    else:
        c.execute("""
            INSERT INTO other (
                pyrus_key,
                is_attachments_enabled,
                is_multi_channel_enabled,
                is_emergency_enabled,
                emergency_template
            ) VALUES (%s, %s, %s, %s, %s)
        """, (pyrus_key, attachments_enabled, multi_channel_enabled, emergency_enabled, emergency_text))

    conn.commit()
    clear_cache(pyrus_key)
    conn.close()

    return redirect("/dashboard")


@site_routes.route("/dashboard/configuration", methods=["POST"])
async def dashboard_configuration():
    if "tenant" not in session:
        return redirect("/")

    tenant_id = session["tenant"]
    form = await request.form

    bot_login = form.get("bot_login", "")
    temperature = float(form.get("temperature", 0.5))
    stop_words = form.get("stop_words", "")
    bot_stop_words = form.get("bot_stop_words", "")
    time_zone = form.get("timezone", "UTC")
    work_from = form.get("work_from", "")
    work_to = form.get("work_to", "")
    work_from_weekend = form.get("work_from_weekend", "")
    work_to_weekend = form.get("work_to_weekend", "")
    offmsg = form.get("offmsg", "")

    conn = get_mysql_connection()
    c = conn.cursor()

    c.execute("SELECT pyrus_key FROM tenants WHERE tenant_id=%s", (tenant_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return redirect("/dashboard")

    pyrus_key = row[0]

    c.execute("SELECT pyrus_key FROM config WHERE pyrus_key=%s", (pyrus_key,))
    exists = c.fetchone()

    if exists:
        c.execute("""
            UPDATE config SET
                bot_login=%s,
                temperature=%s,
                stop_words=%s,
                bot_stop_words=%s,
                time_zone=%s,
                work_from=%s,
                work_to=%s,
                work_from_weekend=%s,
                work_to_weekend=%s,
                offmsg=%s
            WHERE pyrus_key=%s
        """, (bot_login, temperature, stop_words, bot_stop_words, time_zone, work_from, work_to,
              work_from_weekend, work_to_weekend, offmsg, pyrus_key))
    else:
        c.execute("""
            INSERT INTO config (
                pyrus_key, bot_login, temperature, stop_words, bot_stop_words, time_zone,
                work_from, work_to, work_from_weekend, work_to_weekend, offmsg
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (pyrus_key, bot_login, temperature, stop_words, bot_stop_words, time_zone,
              work_from, work_to, work_from_weekend, work_to_weekend, offmsg))

    conn.commit()
    clear_cache(pyrus_key)
    conn.close()

    return redirect("/dashboard")


@site_routes.route("/dashboard/template", methods=["POST"])
async def dashboard_bot_template():
    if "tenant" not in session:
        return redirect("/")

    tenant_id = session["tenant"]
    bot_template = (await request.form).get("bot_template", "").strip()

    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("SELECT pyrus_key FROM tenants WHERE tenant_id=%s", (tenant_id,))
    row = c.fetchone()
    if row:
        pyrus_key = row[0]
        c.execute("INSERT INTO template (pyrus_key, template) VALUES (%s, %s) ON DUPLICATE KEY UPDATE template=%s", (pyrus_key, bot_template, bot_template))
        conn.commit()
        clear_cache(pyrus_key)
    conn.close()

    return redirect("/dashboard")

