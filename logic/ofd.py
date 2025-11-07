from quart import jsonify
from logic.core import approve, is_approved
from logic.cache import get_cache_config
from logic.regform_updater import tasks_today

question = {}
positive_answers = {"да", "конечно", "ага", "угу", "разумеется", "согласен", "похож", "1"}
negative_answers = {"нет", "неа", "никак", "ни в коем случае", "отказываюсь", "несогласен", "2"}

async def check(task, id, sessions, answer, pyrus_key, tenant_id):
    try:
        if task["is_closed"] or await is_approved(id):
            print("Closed"); return jsonify({})
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

        if text := comment.get("text"): print(f"{channel}\n{text}")

        if attachs := task.get('attachments'):
            if (url := attachs[-1].get('url')):
                return await approve(sessions, id, config, pyrus_key, task, tenant_id)
        
        if id not in question:
            greeting = config["ofd"]["greeting"]
            resp = {
                "text": greeting,
                "channel": {"type": channel}
            }
            question[id] = True
            return jsonify(resp)

        lowtext = text.lower()

        if id not in answer:
            if lowtext in positive_answers:
                template = config["ofd"]["template"]
                resp = {
                    "text": template,
                    "channel": {"type": channel},
                    "approval_choice": "approved"
                }

                answer[id] = True
                tasks_today[tenant_id] = tasks_today.get(tenant_id, 0) + 1 
                return jsonify(resp)
            
            if lowtext in negative_answers:
                resp = {"text": "Уточните название заведения и ваш вопрос", "channel": {"type": channel}}
                answer[id] = True
                return jsonify(resp)
            
            return jsonify({"text": "Ответьте да или нет", "channel": {"type": channel}})
        
    except KeyError as e: print(f"KeyError: {e}")
    return jsonify({})