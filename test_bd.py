import mysql.connector
import bcrypt

def init_db():
    conn = mysql.connector.connect(
        host="mysql.railway.internal",
        port=3306,
        user="root",
        password="mKsqCRzLYqBKtHkTKiVpfFADjGMsdcLm",
        database="railway"
    )
    c = conn.cursor()

    # tenants
    c.execute("""
    CREATE TABLE IF NOT EXISTS tenants (
        tenant_id VARCHAR(255) PRIMARY KEY,
        pyrus_key VARCHAR(255) UNIQUE
    )
    """)

    # users
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        tenant_id VARCHAR(255),
        login VARCHAR(255),
        password VARCHAR(255),
        FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
    )
    """)

    # admins
    c.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        login VARCHAR(255) PRIMARY KEY,
        password VARCHAR(255)
    )
    """)

    # ofd
    c.execute("""
    CREATE TABLE IF NOT EXISTS ofd (
        pyrus_key VARCHAR(255) UNIQUE,
        ofd_enabled BOOLEAN,
        ofd_day INT,
        ofd_greeting TEXT,
        ofd_template TEXT,
        FOREIGN KEY (pyrus_key) REFERENCES tenants(pyrus_key)
    )
    """)

    # config
    c.execute("""
    CREATE TABLE IF NOT EXISTS config (
        pyrus_key VARCHAR(255) UNIQUE,
        temperature FLOAT,
        stop_words TEXT,
        time_zone VARCHAR(255),
        work_from VARCHAR(255),
        work_to VARCHAR(255),
        offmsg TEXT,
        bot_stop_words TEXT,
        bot_login TEXT,
        FOREIGN KEY (pyrus_key) REFERENCES tenants(pyrus_key)
    )
    """)

    """try:
        c.execute("ALTER TABLE config ADD COLUMN bot_stop_words TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE config ADD COLUMN bot_login TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE config ADD COLUMN work_from_weekend VARCHAR(255)")
    except:
        pass
    try:
        c.execute("ALTER TABLE config ADD COLUMN work_to_weekend VARCHAR(255)")
    except:
        pass
    """

    # form
    c.execute("""
    CREATE TABLE IF NOT EXISTS form (
        pyrus_key VARCHAR(255) UNIQUE,
        form_enabled BOOLEAN,
        dictionary_id VARCHAR(255),
        dict_field_id VARCHAR(255),
        name_id VARCHAR(255),
        issue_id VARCHAR(255),
        solution_id VARCHAR(255),
        request_type_id VARCHAR(255),
        form_template TEXT,
        FOREIGN KEY (pyrus_key) REFERENCES tenants(pyrus_key)
    )
    """)
    """try:
        c.execute("ALTER TABLE form ADD COLUMN form_enabled BOOLEAN")
    except:
        pass
    try:
        c.execute("ALTER TABLE form ADD COLUMN form_template TEXT")
    except:
        pass
    """
    # template
    c.execute("""
    CREATE TABLE IF NOT EXISTS template (
        pyrus_key VARCHAR(255) UNIQUE,
        template TEXT,
        FOREIGN KEY (pyrus_key) REFERENCES tenants(pyrus_key)
    )
    """)

    # api_keys
    c.execute("""
    CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY,
        openai_api_key TEXT,
        ocr_api_key TEXT,
        assembly_api_key TEXT
    )
    """)

    # other
    c.execute("""
    CREATE TABLE IF NOT EXISTS other (
        pyrus_key VARCHAR(255) UNIQUE,
        is_attachments_enabled BOOLEAN,
        is_emergency_enabled BOOLEAN,
        emergency_template TEXT,
        FOREIGN KEY (pyrus_key) REFERENCES tenants(pyrus_key)
    )
    """)

    try:
        c.execute("ALTER TABLE users ADD UNIQUE (login)")
    except:
        pass

    # Добавление администратора
    login = "admin"
    raw_password = "password"
    hashed_password = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Проверка — есть ли уже админ
    c.execute("SELECT login FROM admins WHERE login = %s", (login,))
    if not c.fetchone():
        c.execute("INSERT INTO admins (login, password) VALUES (%s, %s)", (login, hashed_password))

    conn.commit()
    c.close()
    conn.close()
