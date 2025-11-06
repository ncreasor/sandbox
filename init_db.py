import bcrypt
from logic.cache import get_mysql_connection
from datetime import datetime, date
def init_db():
    conn = get_mysql_connection()
    c = conn.cursor()

    # модели гпт
    c.execute("""
    CREATE TABLE IF NOT EXISTS gpt_models (
        model_name VARCHAR(100) PRIMARY KEY
    )
    """)
    # заведения
    c.execute("""
    CREATE TABLE IF NOT EXISTS tenants (
        tenant_id VARCHAR(255) PRIMARY KEY,
        pyrus_key VARCHAR(255) UNIQUE,
        gpt_model VARCHAR(100),
        allow_attachments_toggle BOOLEAN DEFAULT FALSE,
        allow_multi_channel_toggle BOOLEAN DEFAULT FALSE,
        FOREIGN KEY (gpt_model) REFERENCES gpt_models(model_name) ON DELETE SET NULL
    )
    """)

    # для других настроек
    c.execute("""
        CREATE TABLE IF NOT EXISTS other (
        pyrus_key VARCHAR(255) PRIMARY KEY,
        is_attachments_enabled BOOLEAN,
        is_multi_channel_enabled BOOLEAN,
        is_emergency_enabled BOOLEAN,
        emergency_template TEXT,
        allow_attachments_toggle BOOLEAN DEFAULT FALSE,
        allow_multi_channel_toggle BOOLEAN DEFAULT FALSE,
        FOREIGN KEY (pyrus_key) REFERENCES tenants(pyrus_key)
    )
    """)

    # юзеры
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        tenant_id VARCHAR(255),
        login VARCHAR(255) UNIQUE,
        password VARCHAR(255),
        FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
    )
    """)
    # админы
    c.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        login VARCHAR(255) PRIMARY KEY,
        password VARCHAR(255)
    )
    """)
        # добавление админа
    #login = "admin1"
    #password = "123"
    #hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    #c.execute("REPLACE INTO admins (login, password) VALUES (%s, %s)", (login, hashed))
    # колонка с параметрами ОФД
    c.execute("""
    CREATE TABLE IF NOT EXISTS ofd (
        pyrus_key VARCHAR(255) PRIMARY KEY,
        ofd_enabled BOOLEAN,
        ofd_day INT,
        ofd_greeting TEXT,
        ofd_template TEXT,
        FOREIGN KEY (pyrus_key) REFERENCES tenants(pyrus_key)
    )
    """)
    # колонка с параметрами
    c.execute("""
    CREATE TABLE IF NOT EXISTS config (
        pyrus_key VARCHAR(255) PRIMARY KEY,
        bot_login TEXT,
        temperature FLOAT,
        stop_words TEXT,
        bot_stop_words TEXT,
        time_zone VARCHAR(255),
        work_from VARCHAR(255),
        work_to VARCHAR(255),
        work_from_weekend VARCHAR(255),
        work_to_weekend VARCHAR(255),
        offmsg TEXT,
        FOREIGN KEY (pyrus_key) REFERENCES tenants(pyrus_key)
    )
    """)
    # колонка с формой
    c.execute("""
    CREATE TABLE IF NOT EXISTS form (
        pyrus_key VARCHAR(255) PRIMARY KEY,
        dictionary_id VARCHAR(255),
        dict_field_id VARCHAR(255),
        name_column VARCHAR(255),
        filter_column VARCHAR(255),
        filter_words TEXT,
        FOREIGN KEY (pyrus_key) REFERENCES tenants(pyrus_key)
    )
    """)
    # шаблон бота
    c.execute("""
    CREATE TABLE IF NOT EXISTS template (
        pyrus_key VARCHAR(255) PRIMARY KEY,
        template TEXT,
        FOREIGN KEY (pyrus_key) REFERENCES tenants(pyrus_key)
    )
    """)
    # для админки
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY,
        openai_api_key TEXT
    )
    """)
    try:
        c.execute("ALTER TABLE api_keys DROP COLUMN assembly_api_key")
    except:
        pass

    # Убедиться что колонка openai_api_key поддерживает длинные ключи
    try:
        c.execute("ALTER TABLE api_keys MODIFY openai_api_key VARCHAR(500)")
    except:
        pass


    c.execute("""
    CREATE TABLE IF NOT EXISTS form_config (
        pyrus_key VARCHAR(255) PRIMARY KEY,
        form_enabled BOOLEAN,
        form_or_card VARCHAR(50),
        form_template TEXT,
        dynamic_fields JSON,
        FOREIGN KEY (pyrus_key) REFERENCES tenants(pyrus_key)
    )
    """)

        
    c.execute("""
    CREATE TABLE IF NOT EXISTS card (
        pyrus_key VARCHAR(255) PRIMARY KEY,
        card_id VARCHAR(255),
        field_id VARCHAR(255),
        FOREIGN KEY (pyrus_key) REFERENCES tenants(pyrus_key)
    )
    """)


    c.execute("""
    CREATE TABLE IF NOT EXISTS reg_form (
        pyrus_key VARCHAR(255) PRIMARY KEY,
        parsed_reg TEXT,
        FOREIGN KEY (pyrus_key) REFERENCES tenants(pyrus_key)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS statistics (
        tenant_id VARCHAR(255),
        date DATE,
        request_count INT DEFAULT 0,
        task_count INT DEFAULT 0,
        PRIMARY KEY (tenant_id),
        FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
    )
    """)
    conn.commit()
    conn.close()
