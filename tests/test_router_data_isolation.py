"""Изоляция данных роутеров при диспетчеризации (issue #221).

Данные, вычисленные фильтрами роутера или записанные его outer
middleware, видны только обработчикам этого роутера. Роутер, который
событие не обработал, не влияет на то, что получат следующие.
"""

from maxapi import F
from maxapi.dispatcher import Dispatcher, Router
from maxapi.filters.filter import BaseFilter
from maxapi.filters.middleware import BaseMiddleware


class DataFilter(BaseFilter):
    """BaseFilter, добавляющий данные в kwargs обработчика."""

    def __init__(self, key: str, value) -> None:
        self.key = key
        self.value = value

    async def __call__(self, event) -> dict:
        return {self.key: self.value}


class CountingFilter(BaseFilter):
    """BaseFilter, считающий свои вызовы."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, event) -> bool:
        self.calls += 1
        return True


class DataMiddleware(BaseMiddleware):
    """Outer middleware, записывающая значение в data."""

    def __init__(self, key: str, value) -> None:
        self.key = key
        self.value = value

    async def __call__(self, handler, event, data):
        data[self.key] = self.value
        return await handler(event, data)


def _make_dp(*routers: Router) -> Dispatcher:
    dp = Dispatcher()
    dp.include_routers(*routers)
    return dp


async def test_router_without_handlers_does_not_leak_filter_data(
    sample_message_created_event,
):
    """Сценарий из issue: у A нет обработчиков, B получает ``args``."""
    a = Router("A")
    a.filter(DataFilter("args", ["from_A"]))
    b = Router("B")
    received = []

    @b.message_created()
    async def handler_b(event, args=None):
        received.append(args)

    await _make_dp(a, b).handle(sample_message_created_event)

    assert received == [None]


async def test_unhandled_router_does_not_leak_filter_data(
    sample_message_created_event,
):
    """Фильтр A прошёл, но ни один его обработчик не подошёл."""
    a = Router("A")
    a.filter(DataFilter("args", ["from_A"]))
    b = Router("B")
    received = []

    @a.message_created(F.message.body.text == "__never__")
    async def handler_a(event, args=None):
        received.append(("A", args))

    @b.message_created()
    async def handler_b(event, args=None):
        received.append(("B", args))

    await _make_dp(a, b).handle(sample_message_created_event)

    assert received == [("B", None)]


async def test_unhandled_router_does_not_leak_outer_middleware_data(
    sample_message_created_event,
):
    """Запись outer middleware необработавшего роутера не видна B."""
    a = Router("A")
    a.register_outer_middleware(DataMiddleware("args", ["from_A"]))
    b = Router("B")
    received = []

    @a.message_created(F.message.body.text == "__never__")
    async def handler_a(event, args=None):
        received.append(("A", args))

    @b.message_created()
    async def handler_b(event, args=None):
        received.append(("B", args))

    await _make_dp(a, b).handle(sample_message_created_event)

    assert received == [("B", None)]


async def test_router_filter_data_reaches_own_handler(
    sample_message_created_event,
):
    """Данные фильтра роутера по-прежнему доходят до его обработчика."""
    a = Router("A")
    a.filter(DataFilter("args", ["from_A"]))
    received = []

    @a.message_created()
    async def handler_a(event, args=None):
        received.append(args)

    await _make_dp(a).handle(sample_message_created_event)

    assert received == [["from_A"]]


async def test_parent_filter_data_reaches_child_handler(
    sample_message_created_event,
):
    """Данные фильтра родителя доходят до обработчика дочернего роутера."""
    parent = Router("parent")
    parent.filter(DataFilter("args", ["from_parent"]))
    child = Router("child")
    parent.include_routers(child)
    received = []

    @child.message_created()
    async def handler_child(event, args=None):
        received.append(args)

    await _make_dp(parent).handle(sample_message_created_event)

    assert received == [["from_parent"]]


async def test_router_filters_skipped_without_handlers_for_event_type(
    sample_message_created_event,
):
    """Фильтры роутера без обработчиков на тип события не вызываются."""
    counting = CountingFilter()
    a = Router("A")
    a.filter(counting)

    @a.message_callback()
    async def handler_a(event):
        pass

    await _make_dp(a).handle(sample_message_created_event)

    assert counting.calls == 0


async def test_handled_router_data_visible_to_global_outer_middleware(
    sample_message_created_event,
):
    """Данные обработавшего роутера видны глобальной outer middleware."""
    seen = []

    class GlobalMiddleware(BaseMiddleware):
        async def __call__(self, handler, event, data):
            result = await handler(event, data)
            seen.append((data.get("args"), data.get("mw")))
            return result

    a = Router("A")
    a.filter(DataFilter("args", ["from_A"]))
    a.register_outer_middleware(DataMiddleware("mw", "from_A_mw"))

    @a.message_created()
    async def handler_a(event):
        pass

    dp = _make_dp(a)
    dp.register_outer_middleware(GlobalMiddleware())
    await dp.handle(sample_message_created_event)

    assert seen == [(["from_A"], "from_A_mw")]
