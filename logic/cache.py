import mysql.connector, os, json
from urllib.parse import urlparse

_cache = {}

def get_mysql_connection():
    url = urlparse(os.getenv("MYSQL_URL"))
    return mysql.connector.connect(
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port,
        database=url.path[1:]
    )

def clear_cache(pyrus_key):
    if pyrus_key in _cache:
        del _cache[pyrus_key]

def clear_all_cache():
    _cache.clear()


def get_pyrus_key(tenant_id):
    conn = get_mysql_connection()
    c = conn.cursor()
    c.execute("SELECT pyrus_key, gpt_model FROM tenants WHERE tenant_id=%s", (tenant_id,))
    row = c.fetchone()
    conn.close()
    return (row[0], row[1]) if row else (None, None)

def get_cache_config(pyrus_key):
    if pyrus_key in _cache:
        return _cache[pyrus_key]

    conn = get_mysql_connection()
    c = conn.cursor()

    c.execute("SELECT ofd_enabled, ofd_day, ofd_greeting, ofd_template FROM ofd WHERE pyrus_key=%s", (pyrus_key,))
    ofd = c.fetchone() or (None,) * 4

    c.execute("SELECT is_attachments_enabled, is_multi_channel_enabled, is_emergency_enabled, emergency_template FROM other WHERE pyrus_key=%s", (pyrus_key,))
    other = c.fetchone() or (False, False, False, None)

    c.execute("SELECT bot_login, temperature, stop_words, bot_stop_words, time_zone, work_from, work_to, work_from_weekend, work_to_weekend, offmsg FROM config WHERE pyrus_key=%s", (pyrus_key,))
    config = c.fetchone() or (None,) * 11

    c.execute("SELECT form_enabled, form_or_card, form_template, dynamic_fields FROM form_config WHERE pyrus_key=%s", (pyrus_key,))
    form_config = c.fetchone() or (None, None, None, "[]")

    c.execute("SELECT card_id, field_id, card_field_id, group_id FROM card WHERE pyrus_key=%s", (pyrus_key,))
    card = c.fetchone() or (None, None, None, None)
    

    c.execute("SELECT dictionary_id, dict_field_id, name_column, filter_column, filter_words FROM form WHERE pyrus_key=%s", (pyrus_key,))
    form = c.fetchone() or (None,) * 5

    c.execute("SELECT openai_api_key FROM api_keys WHERE id=1")
    api_keys = c.fetchone() or (None)

    c.execute("SELECT template FROM template WHERE pyrus_key=%s", (pyrus_key,))
    template = c.fetchone()
        
    c.execute("SELECT parsed_reg FROM reg_form WHERE pyrus_key=%s", (pyrus_key,))
    parsed_reg = c.fetchone()
    
    conn.close()

    _cache[pyrus_key] = {
        "ofd": {
            "enabled": ofd[0],
            "day": ofd[1],
            "greeting": ofd[2],
            "template": ofd[3]
        },
        "other": {
            "attachments_enabled": other[0],
            "multi_channel_enabled": other[1],
            "emergency_enabled": other[2],
            "emergency_template": other[3]
        },
        "config": {
            "bot_login": config[0],
            "temperature": config[1],
            "stop_words": config[2],
            "bot_stop_words": config[3],
            "time_zone": config[4],
            "work_from": config[5],
            "work_to": config[6],
            "work_from_weekend": config[7],
            "work_to_weekend": config[8],
            "offmsg": config[9]
        },
        "form_config": {
            "enabled": form_config[0],
            "form_or_card": form_config[1],
            "form_template": form_config[2],
            "dynamic_fields": json.loads(form_config[3] or "[]")
        },
        "form": {
            "dictionary_id": form[0],
            "dict_field_id": form[1],
            "name_column": form[2],
            "filter_column": form[3],
            "filter_words": form[4],
        },
        "card": {
            "card_id": card[0],
            "field_id": card[1],
            "card_field_id": card[2],
            "group_id": card[3],
        },
        "api_keys": {
            "openai_api_key": api_keys[0],
        },
        "template": template[0] if template else None,
        "parsed_reg": parsed_reg[0] if parsed_reg else None
    }

    return _cache[pyrus_key]
