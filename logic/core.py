import openai # linganguliguliguliwacalingangulingang8
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from quart import jsonify
from logic.atts import inf
from logic.serv import flds, template
from logic.cache import get_cache_config
from logic.regform_updater import tasks_today

approved = set()
processed = set()

# Вспомогательные функции для Assistants API
async def create_or_get_thread(sessions, id, client):
    """Создает новый thread или возвращает существующий"""
    if id not in sessions:
        thread = await client.beta.threads.create()
        sessions[id] = {"thread_id": thread.id}
    return sessions[id]["thread_id"]

async def get_thread_messages(client, thread_id):
    """Получает все сообщения из thread для заполнения полей"""
    messages = await client.beta.threads.messages.list(thread_id=thread_id)
    return [{"role": msg.role, "content": msg.content[0].text.value} for msg in reversed(messages.data)]

# Одобрение задачи
async def approve(sessions, id, config, pyrus_key, task, tenant_id): # https://surl.li/gbpscn
    response = {"approval_choice": "approved"}
    # Обновление полей задачи
    if id in sessions:
        if config["form_config"]["enabled"]:
            response.update(await flds(sessions, id, pyrus_key, task))

    sessions.pop(id, None)
    approved.add(id)
    tasks_today[tenant_id] = tasks_today.get(tenant_id, 0) + 1 

    return jsonify(response)

def is_working_now(config: dict):
    tz = ZoneInfo(f"Etc/GMT{-int(config['config']['time_zone'])}")
    now = datetime.now(tz)
    start_str = config["config"]["work_from"] if now.weekday() < 5 else config["config"]["work_from_weekend"]
    end_str = config["config"]["work_to"] if now.weekday() < 5 else config["config"]["work_to_weekend"]

    start = datetime.strptime(start_str, "%H:%M").time()
    end = datetime.strptime(end_str, "%H:%M").time()
    now_time = now.time()

    if start <= end:
        return start <= now_time < end
    else:  # переход через полночь
        return now_time >= start or now_time < end


# Обработка задачи
async def processing(task, id, sessions, pyrus_key, model, client, tenant_id):
    try:
        if task["is_closed"] or id in approved:
            return jsonify({})
        
        config = get_cache_config(pyrus_key)

        # Получение типа канала
        check_channel = task.get("comments", [{}])[0].get("channel", {}).get("type")

        if check_channel == "custom":
            return await approve(sessions, id, config, pyrus_key, task, tenant_id)

        channel = None
        if config["other"]["multi_channel_enabled"]:
            channel = check_channel
        elif check_channel == "telegram":
            channel = "telegram"

        if not channel:
            return jsonify({})

        # Получение последнего комментария
        comment = task["comments"][-1]
        stop_words = [w.strip().lower() for w in config["config"]["stop_words"].split(",")]
        if any(word in str(task).lower() for word in stop_words):
            print("restoit or thanks")
            return await approve(sessions, id, config, pyrus_key, task, tenant_id)

        # Проверка, является ли автор комментария инженером
        if comment.get("author", {}).get("position"):
            print("Engineer")

            return await approve(sessions, id, config, pyrus_key, task, tenant_id)

        # Получение текста комментария
        text = comment.get("text", "")
        if text=="test":
            print(task)
            
        attach_text = ""
        attachs = task.get("attachments") or []

        if attachs and not config["other"]["attachments_enabled"]:
            return await approve(sessions, id, config, pyrus_key, task, tenant_id)

        if attachs:
            if (url := attachs[-1].get("url")) and url not in processed:
                attach_text = await inf(url, attachs[-1].get("name"), pyrus_key)
                processed.add(url)

        if not text and not attach_text:
            return await approve(sessions, id, config, pyrus_key, task, tenant_id)

        full_text = f"{attach_text}\n{text}".strip()

        print(f"{tenant_id}: ({channel}: {full_text})")

        if tenant_id == "restoit" and task["form_id"] == 2328354:
            print("integrations")
            return await integrations(sessions, full_text, channel, id, config, model, task, client, tenant_id)
        
        return await prep(sessions, full_text, channel, id, pyrus_key, config, model, task, client, tenant_id)

    except KeyError as e: print(f"KeyError: {e}")
    return jsonify({})




async def integrations(sessions, text, channel, id, config, model, task, client, tenant_id):
    resptext = await integrations_question(id, text, sessions, config, model, client, tenant_id)
    response = {"text": resptext, "channel": {"type": channel}, "form_id": "2328354",}
    if not is_working_now(config):
        response["text"] += f"\n\n{config['config']['offmsg']}"
    
    bot_stop_words = [w.strip().lower() for w in config["config"]["bot_stop_words"].split(",")]
    if any(word in resptext.lower() for word in bot_stop_words):
        response["approval_choice"] = "approved"
        sessions.pop(id, None)
        approved.add(id)
        tasks_today[tenant_id] = tasks_today.get(tenant_id, 0) + 1

    print("integrations:", resptext)
    return jsonify(response)

async def integrations_question(id, text, sessions, config, model, client, tenant_id, retry=0, max_retries=2):
    try:
        thread_id = await create_or_get_thread(sessions, id, client)
        assistant_id = await get_or_create_assistant(tenant_id, "integrations", config, model, client)

        # Проверяем активные runs и ждем их завершения
        runs = await client.beta.threads.runs.list(thread_id=thread_id, limit=1)
        if runs.data and runs.data[0].status in ["queued", "in_progress"]:
            print(f"Waiting for active run {runs.data[0].id} to complete...")
            active_run = runs.data[0]
            while active_run.status in ["queued", "in_progress"]:
                await asyncio.sleep(0.3)
                active_run = await client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=active_run.id)

        # Добавляем сообщение пользователя
        await client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=text
        )

        # Запускаем assistant
        run = await client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            temperature=config["config"]["temperature"]
        )

        # Ждем завершения
        while run.status in ["queued", "in_progress"]:
            await asyncio.sleep(0.3)
            run = await client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)

        if run.status == "completed":
            messages = await client.beta.threads.messages.list(thread_id=thread_id)
            resptext = messages.data[0].content[0].text.value.strip()

            # Проверка доли английских символов
            eng_ratio = sum(c.isascii() and c.isalpha() for c in resptext) / max(1, len(resptext))
            if eng_ratio > 0.5 and retry < max_retries:
                print(f"Ответ слишком на английском, повторяем запрос {retry+1}/{max_retries}")
                print("Ответ:", resptext)
                return await integrations_question(id, text, sessions, config, model, client, tenant_id, retry + 1, max_retries)

            return resptext
        else:
            print(f"Run failed: {run.status}")
            return ""

    except Exception as e:
        print("openai error:", e)
        return ""





# Подготовка ответа
async def prep(sessions, text, channel, id, pyrus_key, config, model, task, client, tenant_id):

    resptext = await question(id, text, sessions, config, model, client, tenant_id)
    if not resptext:
        print("not resptext")
        return jsonify({})
    response = {"text": resptext, "channel": {"type": channel}}
    
    # Определение рабочего времени
    if not is_working_now(config):
        response["text"] += f"\n\n{config['config']['offmsg']}"

    if config["other"]["emergency_enabled"]:
        response["text"] += f"\n\n{config['other']['emergency_template']}"

    # Проверка на наличие Anydesk или ..
    bot_stop_words = [w.strip().lower() for w in config["config"]["bot_stop_words"].split(",")]
    if any(word in resptext.lower() for word in bot_stop_words):
        response["approval_choice"] = "approved"

        # Обновление полей задачи
        if config["form_config"]["enabled"]:
            response.update(await flds(sessions, id, pyrus_key, task))
        sessions.pop(id, None)
        approved.add(id)
        tasks_today[tenant_id] = tasks_today.get(tenant_id, 0) + 1 

    print(resptext)
    return jsonify(response)

# Создание или получение assistant для tenant
async def get_or_create_assistant(tenant_id, assistant_type, config, model, client):
    from app import tenant_assistants, assistants_lock

    async with assistants_lock:
        if tenant_id not in tenant_assistants:
            tenant_assistants[tenant_id] = {}

        if assistant_type not in tenant_assistants[tenant_id]:
            if assistant_type == "main":
                instructions = f"ВНИМАНИЕ! ВСЕ ОТВЕТЫ ТОЛЬКО НА РУССКОМ. Ты — сотрудник техподдержки. Отвечай вежливо и кратко.\n\n[ИНСТРУКЦИЯ]\n{config['template']}"
                name = f"Support Bot - {tenant_id}"
            else:  # integrations
                from logic.serv import template
                template_text = template("logic/integrations_template.txt")
                instructions = f"ВНИМАНИЕ! ВСЕ ОТВЕТЫ ТОЛЬКО НА РУССКОМ. Ты — сотрудник техподдержки. Отвечай вежливо и кратко.\n\n[ИНСТРУКЦИЯ]\n{template_text}"
                name = f"Integrations Bot - {tenant_id}"

            assistant = await client.beta.assistants.create(
                name=name,
                instructions=instructions,
                model=model
            )
            tenant_assistants[tenant_id][assistant_type] = assistant.id
            print(f"Created {assistant_type} assistant for {tenant_id}: {assistant.id}")

        return tenant_assistants[tenant_id][assistant_type]

# Обработка вопроса
async def question(id, text, sessions, config, model, client, tenant_id, retry=0, max_retries=2):
    try:
        thread_id = await create_or_get_thread(sessions, id, client)
        assistant_id = await get_or_create_assistant(tenant_id, "main", config, model, client)

        # Проверяем активные runs и ждем их завершения
        runs = await client.beta.threads.runs.list(thread_id=thread_id, limit=1)
        if runs.data and runs.data[0].status in ["queued", "in_progress"]:
            print(f"Waiting for active run {runs.data[0].id} to complete...")
            active_run = runs.data[0]
            while active_run.status in ["queued", "in_progress"]:
                await asyncio.sleep(0.3)
                active_run = await client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=active_run.id)

        # Добавляем сообщение пользователя
        await client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=text
        )

        # Запускаем assistant
        run = await client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            temperature=config["config"]["temperature"]
        )

        # Ждем завершения
        while run.status in ["queued", "in_progress"]:
            await asyncio.sleep(0.3)
            run = await client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)

        if run.status == "completed":
            messages = await client.beta.threads.messages.list(thread_id=thread_id)
            resptext = messages.data[0].content[0].text.value.strip()

            # Проверка доли английских символов
            eng_ratio = sum(c.isascii() and c.isalpha() for c in resptext) / max(1, len(resptext))
            if eng_ratio > 0.5 and retry < max_retries:
                print(f"Ответ слишком на английском, повторяем запрос {retry+1}/{max_retries}")
                print("Ответ:", resptext)
                return await question(id, text, sessions, config, model, client, tenant_id, retry + 1, max_retries)

            return resptext
        else:
            print(f"Run failed: {run.status}")
            return ""

    except Exception as e:
        print("openai error:", e)
        return ""
