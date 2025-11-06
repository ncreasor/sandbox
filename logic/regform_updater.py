import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo
from logic.cache import get_cache_config, clear_all_cache, get_mysql_connection
from logic.atts import acs

requests_today = {}
tasks_today = {}

async def dump_stats():
    print("dump_stats started")
    if not requests_today and not tasks_today:
        return

    conn = get_mysql_connection()
    c = conn.cursor()
    tenant_ids = set(requests_today) | set(tasks_today)

    for tenant_id in tenant_ids:
        request_count = requests_today.get(tenant_id, 0)
        task_count = tasks_today.get(tenant_id, 0)
        c.execute("""
            INSERT INTO statistics (tenant_id, request_count, task_count)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                request_count = request_count + VALUES(request_count),
                task_count = task_count + VALUES(task_count)
        """, (tenant_id, request_count, task_count))

    conn.commit()
    c.close()
    conn.close()
    requests_today.clear()
    tasks_today.clear()

async def reset_stats():
    print("reset_stats started")
    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("UPDATE statistics SET request_count = 0, task_count = 0")
    conn.commit()
    c.close()
    conn.close()


def get_all_pyrus_keys():
    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("SELECT pyrus_key FROM tenants")
    keys = [row[0] for row in c.fetchall()]
    c.close()
    conn.close()
    return keys

async def form_register():
    print("form_register started")
    keys = get_all_pyrus_keys()
    for pyrus_key in keys:
        config = get_cache_config(pyrus_key)
        if config["form_config"]["form_or_card"] == "card":
            print("updating")
            await update_reg_form(pyrus_key, config)
    print("success")
    clear_all_cache()

async def update_reg_form(pyrus_key, config):
    token = await acs(config, pyrus_key)
    form_id = config["card"]["card_id"]
    field_id = config["card"]["field_id"]
    if form_id and field_id:
        form_id = int(form_id)
        field_id = int(field_id)
    else:
        print("missing key")
        return

    url = f'https://api.pyrus.com/v4/forms/{form_id}/register'
    params = {
        "include_archived": "y",
        "field_ids": str(field_id)
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers={"Authorization": f"Bearer {token}"}, params=params) as resp:
            data = await resp.json()

    rows = []
    for task in data.get("tasks", []):
        value = next((f.get("value") for f in task.get("fields", []) if f.get("id") == field_id), None)
        if value:
            rows.append({"id": task["id"], "value": value})

    list_str = "\n".join(f"{r['id']}: {r['value']}" for r in rows)

    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO reg_form (pyrus_key, parsed_reg)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE parsed_reg = VALUES(parsed_reg)
    """, (pyrus_key, list_str))
    conn.commit()
    c.close()
    conn.close()

# Настройка шедулера
scheduler = AsyncIOScheduler()
trigger = CronTrigger(hour=3, minute=0, timezone=ZoneInfo("Asia/Almaty"))
scheduler.add_job(form_register, trigger)

dump_trigger = CronTrigger(hour=23, minute=59, timezone=ZoneInfo("Asia/Almaty"))
scheduler.add_job(dump_stats, dump_trigger)

# 1-го числа каждого месяца в 00:00
reset_trigger = CronTrigger(day=1, hour=0, minute=0, timezone=ZoneInfo("Asia/Almaty"))
scheduler.add_job(reset_stats, reset_trigger)