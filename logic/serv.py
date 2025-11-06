import re, aiohttp
from openai import AsyncOpenAI
from logic.atts import acs
from logic.cache import get_cache_config

def normalize_phone(phone):
    phone = phone.strip()
    if phone.startswith("8"):
        phone = "+7" + phone[1:]
    return phone

# Получение шаблона
def template(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read().strip()


# Поиск заведения по названию
async def match(keyword, config, token, session, api_key):
    data = await catalog(config, token, session)
    name_col = int(config["form"]["name_column"]) - 1
    filter_col = config["form"].get("filter_column")
    filter_words_raw = config["form"].get("filter_words", "").strip()

    if filter_col and filter_words_raw:
        filter_col = int(filter_col) - 1
        filter_words = [w.strip() for w in filter_words_raw.split(",")]
        rows = [
            {"id": item["item_id"], "name": item["values"][name_col]}
            for item in data["items"]
            if item["values"][name_col].strip() and item["values"][filter_col] in filter_words
        ]
    else:
        rows = [
            {"id": item["item_id"], "name": item["values"][name_col]}
            for item in data["items"]
            if item["values"][name_col].strip()
        ]

    template = [
        {"role": "system", "content": "Твоя задача - проанализировать входящее значение и найти наиболее похожее в предоставленном списке. Верни ТОЛЬКО числовой ID найденного элемента. Если подходящих элементов нет или их несколько — верни '-'"},
        {"role": "user", "content": f"Искомое значение: {keyword}\n\nСписок элементов:\n" + "\n".join([f"{item['id']}: {item['name']}" for item in rows])}
    ]
    return await openai_name(template, api_key)

async def match_card(keyword, config, api_key):
    if not config["parsed_reg"]:
        print("-")
        return "-"
    list_str = config["parsed_reg"]
    template = [
        {
            "role": "system",
            "content": (
                "Твоя задача - проанализировать входящее значение и найти наиболее похожее в предоставленном списке. "
                "Верни ТОЛЬКО числовой ID найденного элемента. "
                "Если подходящих элементов нет или их несколько — верни '-'"
            )
        },
        {
            "role": "user",
            "content": f"Искомое значение: {keyword}\n\nСписок элементов:\n{list_str}"
        },
    ]

    return await openai_name(template, api_key)


# Получение каталога заведений
async def catalog(config, token, session):
    dictionary_id = config["form"]["dictionary_id"]
    url = f"https://api.pyrus.com/v4/catalogs/{dictionary_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers={"Authorization": f"Bearer {token}"}) as response:
            return await response.json()

async def get_task_fields(task_id, token, session):
    url = f"https://api.pyrus.com/v4/tasks/{task_id}"
    async with session.get(url, headers={"Authorization": f"Bearer {token}"}) as resp:
        data = await resp.json()
    return data["task"]["fields"]

async def fill_task_fields(gid, item_fields_data, current_task_fields):

    title_block = next(f for f in current_task_fields if f['id'] == gid)
    target_fields = {f['name']: f['id'] for f in title_block['value']['fields']}
    updates = []

    for item_field in item_fields_data:
        name = item_field['name']
        value = item_field.get('value')
        if not value or name not in target_fields:
            continue

        field_id = target_fields[name]

        if item_field['type'] == 'catalog' and isinstance(value, dict):
            updates.append({
                'id': field_id,
                'value': {'item_id': value['item_id']}
            })
        else:
            updates.append({'id': field_id, 'value': value})

    return updates



# Получение полей задачи
async def flds(sessions, id, pyrus_key, task):
    try:
        config = get_cache_config(pyrus_key)
        api_key = config["api_keys"]["openai_api_key"]

        # Получаем всю историю диалога из thread для анализа
        if id in sessions and "thread_id" in sessions[id]:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key)

            # Получаем все сообщения из thread
            messages = await client.beta.threads.messages.list(thread_id=sessions[id]["thread_id"])
            dialog_history = []
            for msg in reversed(messages.data):
                role = "user" if msg.role == "user" else "assistant"
                content = msg.content[0].text.value
                dialog_history.append({"role": role, "content": content})

            # Создаем запрос для извлечения полей на основе всей истории
            field_extraction_messages = [
                {"role": "system", "content": config["form_config"]["form_template"]}
            ] + dialog_history
        else:
            # Fallback для случаев, когда нет thread
            field_extraction_messages = [
                {"role": "system", "content": config["form_config"]["form_template"]},
                {"role": "user", "content": "Нет истории диалога"}
            ]

        fields = await openai_resp_direct(field_extraction_messages, api_key)
        matches = re.findall(r'"(.*?)"', fields)
        dynamic_fields = config["form_config"].get("dynamic_fields", [])
        resp = {"field_updates": []}

        for i, field in enumerate(dynamic_fields):
            val = matches[i] if i < len(matches) else ""
            if field["type"] == "phone":
                value = normalize_phone(val)
            elif field["type"] == "money":
                try: value = float(val.replace(",", "."))
                except: value = 0.0
            elif field["type"] == "select":
                value = {"item_name": val}
            else:
                value = val
            resp["field_updates"].append({"id": field["id"], "value": value})

        if config["form_config"]["form_or_card"] != "":
            keyword = matches[0] if len(matches) > 0 else ""
            if keyword.strip() == "":
                return resp

            token = await acs(config, pyrus_key)
            async with aiohttp.ClientSession() as session:
                if config["form_config"]["form_or_card"] == "form":
                    item_id = await match(keyword, config, token, session, api_key)
                    print("form filling finished:", item_id)
                    if item_id != "-":
                        resp["field_updates"].append({"id": config["form"]["dict_field_id"], "value": {"item_id": int(item_id)}})
                elif config["form_config"]["form_or_card"] == "card":
                    item_id = await match_card(keyword, config, api_key)
                    if item_id != "-":
                        resp["field_updates"].append({"id": config["card"]["card_field_id"], "value": {"task_id": item_id}})
                        print("card filling finished:", item_id)
                        if config["card"]["group_id"]:
                            gr_id = int(config["card"]["group_id"])
                            updates = await fill_task_fields(gr_id, await get_task_fields(item_id, token, session), task["fields"])
                            resp["field_updates"].extend(updates)

        return resp

    except Exception as e:
        print("error:", e)
        return ""


# Получение полей от GPT (старая функция для совместимости)
async def openai_resp(sessions, id, api_key):
    try:
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=sessions[id],
            max_tokens=80,
            temperature=0.1
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("openai error", e)
        return ""

# Новая функция для прямого вызова с messages
async def openai_resp_direct(messages, api_key):
    try:
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=80,
            temperature=0.1
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("openai error", e)
        return ""

async def openai_name(template, api_key):
    try:
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=template,
            max_tokens=40,
            temperature=0.2
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("openai error", e)
        return ""
