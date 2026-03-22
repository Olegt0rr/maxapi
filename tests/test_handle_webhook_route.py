import pytest

pytest.importorskip("fastapi")


import maxapi.dispatcher as dispatcher_module
from fastapi import Request
from fastapi.testclient import TestClient
from maxapi.dispatcher import DEFAULT_PATH, Dispatcher
from maxapi.types.updates import UNKNOWN_UPDATE_DISCLAIMER


async def test_handle_webhook_unknown_update_logs_and_returns_ok(
    monkeypatch, caplog
):
    """Если process_update_webhook вернул None, ручка должна
    залогировать предупреждение и вернуть {'ok': True} с кодом 200.
    При этом dp.handle вызываться не должен.
    """
    # Подготовка диспетчера
    dp = Dispatcher()

    # Подменяем init_serve, чтобы не запускать uvicorn
    async def fake_init_serve(*args, **kwargs):
        return None

    dp.init_serve = fake_init_serve

    # Отмечаем, что uvicorn доступен для обхода проверки
    monkeypatch.setattr(dispatcher_module, "UVICORN_INSTALLED", True)

    # Гарантируем наличие Request в модуле dispatcher
    monkeypatch.setattr(dispatcher_module, "Request", Request, raising=False)

    # Подменяем парсер webhook, чтобы он возвращал None
    async def fake_process_update_webhook(event_json, bot):
        return None

    monkeypatch.setattr(
        dispatcher_module,
        "process_update_webhook",
        fake_process_update_webhook,
    )

    # Подменяем dp.handle, чтобы отследить вызовы
    called = False

    async def fake_handle(event_object):
        nonlocal called
        called = True

    dp.handle = fake_handle

    # Регистрируем ручку через handle_webhook
    class DummyBot:
        pass

    await dp.handle_webhook(bot=DummyBot())

    client = TestClient(dp.webhook_app)

    payload = {"update_type": "SOME_UNKNOWN"}
    caplog.clear()
    resp = client.post("/", json=payload)

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    # Проверяем, что в логах присутствует ожидаемое сообщение
    expected_msg = UNKNOWN_UPDATE_DISCLAIMER.format(
        update_type=payload.get("update_type")
    )
    found = any(expected_msg in rec.getMessage() for rec in caplog.records)
    assert found
    assert called is False


class DummyEvent:
    def __init__(self, update_type="MESSAGE_CREATED"):
        self.update_type = update_type

    def get_ids(self):
        return (123, 456)


async def test_handle_webhook_with_event_calls_handle_and_returns_ok(
    monkeypatch,
):
    """Если process_update_webhook вернул объект события, ручка должна
    вызвать dp.handle и вернуть {'ok': True} с кодом 200.
    """
    dp = Dispatcher()

    async def fake_init_serve(*args, **kwargs):
        return None

    dp.init_serve = fake_init_serve

    monkeypatch.setattr(dispatcher_module, "UVICORN_INSTALLED", True)

    # Гарантируем наличие Request в модуле dispatcher
    monkeypatch.setattr(dispatcher_module, "Request", Request, raising=False)

    # Создаём объект события для возврата парсером
    event = DummyEvent(update_type="MESSAGE_CREATED")

    async def fake_process_update_webhook(event_json, bot):
        return event

    monkeypatch.setattr(
        dispatcher_module,
        "process_update_webhook",
        fake_process_update_webhook,
    )

    handled = {}

    async def fake_handle(event_object):
        # Сохраняем объект для последующей проверки
        handled["obj"] = event_object

    dp.handle = fake_handle

    class DummyBot:
        pass

    await dp.handle_webhook(bot=DummyBot())

    client = TestClient(dp.webhook_app)

    payload = {"update_type": "MESSAGE_CREATED", "payload": {"x": 1}}
    resp = client.post("/", json=payload)

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    # проверяем, что обработчик был вызван нашим объектом
    assert handled.get("obj") is event


async def test_handle_webhook_default_path_serves_at_root(monkeypatch):
    """При path по умолчанию (DEFAULT_PATH) ручка доступна по POST /."""
    dp = Dispatcher()

    async def fake_init_serve(*args, **kwargs):
        return None

    dp.init_serve = fake_init_serve
    monkeypatch.setattr(dispatcher_module, "UVICORN_INSTALLED", True)
    monkeypatch.setattr(dispatcher_module, "Request", Request, raising=False)

    async def fake_process_update_webhook(event_json, bot):
        return None

    monkeypatch.setattr(
        dispatcher_module,
        "process_update_webhook",
        fake_process_update_webhook,
    )

    async def fake_handle_noop(event_object):
        pass

    dp.handle = fake_handle_noop

    class DummyBot:
        pass

    await dp.handle_webhook(bot=DummyBot(), path=DEFAULT_PATH)

    client = TestClient(dp.webhook_app)
    resp = client.post("/", json={"update_type": "unknown"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


async def test_handle_webhook_custom_path_serves_at_that_path(monkeypatch):
    """При path ручка доступна по этому пути; POST / возвращает 404."""
    dp = Dispatcher()

    async def fake_init_serve(*args, **kwargs):
        return None

    dp.init_serve = fake_init_serve
    monkeypatch.setattr(dispatcher_module, "UVICORN_INSTALLED", True)
    monkeypatch.setattr(dispatcher_module, "Request", Request, raising=False)

    event = DummyEvent(update_type="MESSAGE_CREATED")

    async def fake_process_update_webhook(event_json, bot):
        return event

    monkeypatch.setattr(
        dispatcher_module,
        "process_update_webhook",
        fake_process_update_webhook,
    )
    handled = {}

    async def fake_handle(event_object):
        handled["obj"] = event_object

    dp.handle = fake_handle

    class DummyBot:
        pass

    webhook_path = "/webhook/custom"
    await dp.handle_webhook(bot=DummyBot(), path=webhook_path)

    client = TestClient(dp.webhook_app)
    payload = {"update_type": "MESSAGE_CREATED", "payload": {}}

    resp_custom = client.post(webhook_path, json=payload)
    assert resp_custom.status_code == 200
    assert resp_custom.json() == {"ok": True}
    assert handled.get("obj") is event

    resp_root = client.post("/", json=payload)
    assert resp_root.status_code == 404


# ---------------------------------------------------------------------------
# Тесты проверки X-Max-Bot-Api-Secret
# ---------------------------------------------------------------------------


def _make_dp_with_secret(monkeypatch, secret: str):
    """Вспомогательная функция: создаёт Dispatcher с webhook_secret."""
    dp = Dispatcher()

    async def fake_init_serve(*args, **kwargs):
        return None

    dp.init_serve = fake_init_serve
    monkeypatch.setattr(dispatcher_module, "UVICORN_INSTALLED", True)
    monkeypatch.setattr(dispatcher_module, "Request", Request, raising=False)

    event = DummyEvent(update_type="MESSAGE_CREATED")

    async def fake_process_update_webhook(event_json, bot):
        return event

    monkeypatch.setattr(
        dispatcher_module,
        "process_update_webhook",
        fake_process_update_webhook,
    )

    handled = {}

    async def fake_handle(event_object):
        handled["obj"] = event_object

    dp.handle = fake_handle

    return dp, handled, event


async def test_handle_webhook_secret_valid_header_passes(monkeypatch):
    """Запрос с верным заголовком X-Max-Bot-Api-Secret должен проходить."""
    secret = "my-secret-123"
    dp, handled, event = _make_dp_with_secret(monkeypatch, secret)

    class DummyBot:
        pass

    await dp.handle_webhook(bot=DummyBot(), webhook_secret=secret)

    client = TestClient(dp.webhook_app)
    payload = {"update_type": "MESSAGE_CREATED", "payload": {}}
    resp = client.post(
        "/",
        json=payload,
        headers={"X-Max-Bot-Api-Secret": secret},
    )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert handled.get("obj") is event


async def test_handle_webhook_secret_wrong_header_returns_401(monkeypatch):
    """Запрос с неверным заголовком X-Max-Bot-Api-Secret должен вернуть 401."""
    secret = "my-secret-123"
    dp, handled, _ = _make_dp_with_secret(monkeypatch, secret)

    class DummyBot:
        pass

    await dp.handle_webhook(bot=DummyBot(), webhook_secret=secret)

    client = TestClient(dp.webhook_app, raise_server_exceptions=False)
    payload = {"update_type": "MESSAGE_CREATED", "payload": {}}
    resp = client.post(
        "/",
        json=payload,
        headers={"X-Max-Bot-Api-Secret": "wrong-secret"},
    )

    assert resp.status_code == 401
    assert resp.json() == {"ok": False, "error": "Unauthorized"}
    assert handled.get("obj") is None


async def test_handle_webhook_secret_missing_header_returns_401(monkeypatch):
    """Запрос без заголовка X-Max-Bot-Api-Secret должен вернуть 401."""
    secret = "my-secret-123"
    dp, handled, _ = _make_dp_with_secret(monkeypatch, secret)

    class DummyBot:
        pass

    await dp.handle_webhook(bot=DummyBot(), webhook_secret=secret)

    client = TestClient(dp.webhook_app, raise_server_exceptions=False)
    payload = {"update_type": "MESSAGE_CREATED", "payload": {}}
    resp = client.post("/", json=payload)

    assert resp.status_code == 401
    assert resp.json() == {"ok": False, "error": "Unauthorized"}
    assert handled.get("obj") is None


async def test_handle_webhook_no_secret_ignores_header(monkeypatch):
    """Если webhook_secret не задан, любой запрос должен проходить."""
    dp = Dispatcher()

    async def fake_init_serve(*args, **kwargs):
        return None

    dp.init_serve = fake_init_serve
    monkeypatch.setattr(dispatcher_module, "UVICORN_INSTALLED", True)
    monkeypatch.setattr(dispatcher_module, "Request", Request, raising=False)

    async def fake_process_update_webhook(event_json, bot):
        return None

    monkeypatch.setattr(
        dispatcher_module,
        "process_update_webhook",
        fake_process_update_webhook,
    )

    async def fake_handle(event_object):
        pass

    dp.handle = fake_handle

    class DummyBot:
        pass

    await dp.handle_webhook(bot=DummyBot())

    client = TestClient(dp.webhook_app)
    payload = {"update_type": "UNKNOWN"}

    # Без заголовка
    resp1 = client.post("/", json=payload)
    assert resp1.status_code == 200

    # С произвольным заголовком
    resp2 = client.post(
        "/",
        json=payload,
        headers={"X-Max-Bot-Api-Secret": "any-value"},
    )
    assert resp2.status_code == 200
