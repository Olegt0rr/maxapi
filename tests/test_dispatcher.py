"""Тесты для Dispatcher и Router."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from maxapi.bot import Bot
from maxapi.context import MemoryContext
from maxapi.dispatcher import Dispatcher, Event, Router
from maxapi.enums.update import UpdateType
from maxapi.filters import F
from maxapi.filters.command import Command, CommandsInfo
from maxapi.filters.handler import Handler
from maxapi.types.updates.bot_started import BotStarted
from maxapi.types.updates.message_created import MessageCreated


class TestDispatcherInitialization:
    """Тесты инициализации Dispatcher."""

    def test_dispatcher_init_default(self):
        """Тест создания Dispatcher с параметрами по умолчанию."""
        dp = Dispatcher()
        assert dp.router_id is None
        assert dp.use_create_task is False
        assert isinstance(dp.event_handlers, list)
        assert len(dp.event_handlers) == 0
        assert isinstance(dp.contexts, dict)
        assert isinstance(dp.routers, list)
        assert isinstance(dp.middlewares, list)
        assert dp.bot is None
        assert dp.polling is False

    def test_dispatcher_init_with_router_id(self):
        """Тест создания Dispatcher с router_id."""
        dp = Dispatcher(router_id="test_id")
        assert dp.router_id == "test_id"

    def test_dispatcher_init_with_use_create_task(self):
        """Тест создания Dispatcher с use_create_task."""
        dp = Dispatcher(use_create_task=True)
        assert dp.use_create_task is True

    def test_dispatcher_events_initialization(self):
        """Тест инициализации событий в Dispatcher."""
        dp = Dispatcher()
        assert hasattr(dp, "message_created")
        assert hasattr(dp, "bot_started")
        assert hasattr(dp, "message_callback")
        assert isinstance(dp.message_created, Event)
        assert isinstance(dp.bot_started, Event)


class TestRouterInitialization:
    """Тесты инициализации Router."""

    def test_router_init_default(self):
        """Тест создания Router."""
        router = Router()
        assert router.router_id is None
        assert isinstance(router, Dispatcher)

    def test_router_init_with_id(self):
        """Тест создания Router с router_id."""
        router = Router(router_id="test_router")
        assert router.router_id == "test_router"


class TestDispatcherHandlers:
    """Тесты регистрации обработчиков."""

    def test_register_message_created_handler(self, dispatcher):
        """Тест регистрации обработчика message_created."""

        @dispatcher.message_created()
        async def _(event: MessageCreated):
            pass

        assert len(dispatcher.event_handlers) == 1
        handler = dispatcher.event_handlers[0]
        assert handler.update_type == UpdateType.MESSAGE_CREATED

    def test_register_multiple_handlers(self, dispatcher):
        """Тест регистрации нескольких обработчиков."""

        @dispatcher.message_created()
        async def handler1(event: MessageCreated):
            pass

        @dispatcher.bot_started()
        async def handler2(event: BotStarted):
            pass

        assert len(dispatcher.event_handlers) == 2

    def test_register_handler_with_filter(self, dispatcher):
        """Тест регистрации обработчика с фильтром."""

        @dispatcher.message_created(F.text == "test")
        async def _(event: MessageCreated):
            pass

        assert len(dispatcher.event_handlers) == 1
        handler = dispatcher.event_handlers[0]
        assert handler.filters is not None

    def test_on_started_handler(self, dispatcher):
        """Тест регистрации обработчика on_started."""

        @dispatcher.on_started()
        async def on_started():
            pass

        assert dispatcher.on_started_func is not None


class TestPrepareHandlers:
    @staticmethod
    def make_handler_with_doc(commands, info):
        def func(): ...

        func.__doc__ = f"""
        commands_info: {info}
        """
        return Handler(
            Command(commands),
            func_event=func,
            update_type=UpdateType.ON_STARTED,
        )

    def test_prepare_handlers_assigns_bot_and_extracts_commands(self):
        bot = Bot(token="test")
        dp = Dispatcher()
        router = Router("r1")

        handler = self.make_handler_with_doc("start", "Запустить бота")
        router.event_handlers.append(handler)

        dp.routers.append(router)

        # до подготовки bot ещё не присвоен
        assert router.bot is None
        assert bot.commands == []

        dp._prepare_handlers(bot)

        # после подготовки router должен иметь ссылку на bot
        assert router.bot is bot

        # команды из handler должны быть добавлены в bot.commands
        assert bot.commands == [
            CommandsInfo(commands=["start"], info="Запустить бота")
        ]

    def test_prepare_handlers_multiple_routers_and_handlers(self):
        bot = Bot(token="test")
        dp = Dispatcher()

        r1 = Router("r1")
        r2 = Router("r2")

        h1 = self.make_handler_with_doc("a", "info1")
        h2 = self.make_handler_with_doc(["b", "c"], "info2")

        r1.event_handlers.append(h1)
        r2.event_handlers.append(h2)

        dp.routers.extend([r1, r2])

        dp._prepare_handlers(bot)

        assert r1.bot is bot
        assert r2.bot is bot

        # порядок добавления соответствует обходу роутеров и обработчиков
        assert bot.commands == [
            CommandsInfo(commands=["a"], info="info1"),
            CommandsInfo(commands=["b", "c"], info="info2"),
        ]

    def test_prepare_handlers_with_no_event_handlers_does_nothing(self):
        bot = Bot(token="test")
        dp = Dispatcher()
        router = Router("r1")

        dp.routers.append(router)

        dp._prepare_handlers(bot)

        assert router.bot is bot
        assert bot.commands == []


class TestDispatcherRouters:
    """Тесты работы с роутерами."""

    def test_include_routers(self, dispatcher):
        """Тест добавления роутеров."""
        router1 = Router(router_id="router1")
        router2 = Router(router_id="router2")

        dispatcher.include_routers(router1, router2)

        assert len(dispatcher.routers) == 2
        assert router1 in dispatcher.routers
        assert router2 in dispatcher.routers

    def test_router_handlers(self, dispatcher):
        """Тест обработчиков в роутере."""
        router = Router(router_id="test_router")

        @router.message_created()
        async def handler(event: MessageCreated):
            pass

        dispatcher.include_routers(router)
        assert len(router.event_handlers) == 1


class TestDispatcherMiddleware:
    """Тесты middleware."""

    def test_add_middleware(self, dispatcher):
        """Тест добавления middleware."""
        # Core Stuff
        from maxapi.filters.middleware import BaseMiddleware

        class TestMiddleware(BaseMiddleware):
            async def __call__(self, handler, event, data):
                return await handler(event, data)

        middleware = TestMiddleware()
        dispatcher.middleware(middleware)

        assert len(dispatcher.middlewares) == 1
        assert dispatcher.middlewares[0] == middleware

    def test_add_outer_middleware(self, dispatcher):
        """Тест добавления outer middleware."""
        # Core Stuff
        from maxapi.filters.middleware import BaseMiddleware

        class TestMiddleware(BaseMiddleware):
            async def __call__(self, handler, event, data):
                return await handler(event, data)

        middleware1 = TestMiddleware()
        middleware2 = TestMiddleware()

        dispatcher.middleware(middleware1)
        dispatcher.outer_middleware(middleware2)

        assert dispatcher.middlewares[0] == middleware2
        assert dispatcher.middlewares[1] == middleware1


class TestDispatcherFilters:
    """Тесты фильтров."""

    def test_add_base_filter(self, dispatcher):
        """Тест добавления базового фильтра."""
        # Core Stuff
        from maxapi.filters.filter import BaseFilter

        class TestFilter(BaseFilter):
            async def __call__(self, event):
                return True

        filter_obj = TestFilter()
        dispatcher.filter(filter_obj)

        assert len(dispatcher.base_filters) == 1
        assert dispatcher.base_filters[0] == filter_obj


class TestDispatcherContext:
    """Тесты работы с контекстом."""

    def test_get_memory_context_new(self, dispatcher):
        """Тест получения нового контекста."""
        context = dispatcher._Dispatcher__get_context(12345, 67890)

        assert isinstance(context, MemoryContext)
        assert context.chat_id == 12345
        assert context.user_id == 67890
        assert len(dispatcher.contexts) == 1

    def test_get_memory_context_existing(self, dispatcher):
        """Тест получения существующего контекста."""
        context1 = dispatcher._Dispatcher__get_context(12345, 67890)
        context2 = dispatcher._Dispatcher__get_context(12345, 67890)

        assert context1 is context2
        assert len(dispatcher.contexts) == 1

    def test_get_memory_context_different_ids(self, dispatcher):
        """Тест получения контекстов для разных ID."""
        context1 = dispatcher._Dispatcher__get_context(12345, 67890)
        context2 = dispatcher._Dispatcher__get_context(54321, 98765)

        assert context1 is not context2
        assert len(dispatcher.contexts) == 2


class TestDispatcherMiddlewareChain:
    """Тесты цепочки middleware."""

    def test_build_middleware_chain(self, dispatcher):
        """Тест построения цепочки middleware."""
        # Core Stuff
        from maxapi.filters.middleware import BaseMiddleware

        call_order = []

        class Middleware1(BaseMiddleware):
            async def __call__(self, handler, event, data):
                call_order.append(1)
                return await handler(event, data)

        class Middleware2(BaseMiddleware):
            async def __call__(self, handler, event, data):
                call_order.append(2)
                return await handler(event, data)

        async def handler(event, data):
            call_order.append(3)
            return "result"

        middleware1 = Middleware1()
        middleware2 = Middleware2()

        chain = dispatcher.build_middleware_chain(
            [middleware1, middleware2], handler
        )

        # Проверяем, что цепочка создана
        # (не вызываем, так как нужен реальный event)
        assert callable(chain)


@pytest.mark.asyncio
class TestDispatcherAsync:
    """Асинхронные тесты Dispatcher."""

    async def test_check_me(self, dispatcher, bot):
        """Тест check_me."""
        dispatcher.bot = bot

        with patch.object(
            bot, "get_me", new_callable=AsyncMock
        ) as mock_get_me:
            mock_me = Mock()
            mock_me.username = "test_bot"
            mock_me.first_name = "Test"
            mock_me.user_id = 123
            mock_get_me.return_value = mock_me

            await dispatcher.check_me()

            assert bot._me == mock_me
            mock_get_me.assert_called_once()

    async def test_process_base_filters(
        self, dispatcher, sample_message_created_event
    ):
        """Тест process_base_filters."""
        # Core Stuff
        from maxapi.filters.filter import BaseFilter

        class TestFilter(BaseFilter):
            async def __call__(self, event):
                return {"test_key": "test_value"}

        filter_obj = TestFilter()
        dispatcher.base_filters.append(filter_obj)

        result = await dispatcher.process_base_filters(
            sample_message_created_event, dispatcher.base_filters
        )

        assert isinstance(result, dict)
        assert result["test_key"] == "test_value"

    async def test_process_base_filters_false(
        self, dispatcher, sample_message_created_event
    ):
        """Тест process_base_filters с возвратом False."""
        # Core Stuff
        from maxapi.filters.filter import BaseFilter

        class TestFilter(BaseFilter):
            async def __call__(self, event):
                return False

        filter_obj = TestFilter()
        dispatcher.base_filters.append(filter_obj)

        result = await dispatcher.process_base_filters(
            sample_message_created_event, dispatcher.base_filters
        )

        assert result is False


class TestDispatcherSubscriptions:
    async def test_check_subscriptions_no_subscriptions(
        self, dispatcher, bot, caplog
    ):
        """Если подписок нет, предупреждение не логируется."""
        dispatcher.bot = bot
        bot.get_subscriptions = AsyncMock(return_value=Mock(subscriptions=[]))

        caplog.set_level("WARNING")
        await dispatcher._check_subscriptions(bot)

        # Проверяем, что предупреждение с ключевой фразой не встречается
        assert not any(
            (
                record.levelname == "WARNING"
                and "БОТ ИГНОРИРУЕТ POLLING!" in record.getMessage()
            )
            for record in caplog.records
        )

    async def test_check_subscriptions_warns_when_subscriptions(
        self, dispatcher, bot, caplog
    ):
        """Если подписки есть, логируется предупреждение с URL'ами."""
        dispatcher.bot = bot
        subs = [Mock(url="https://a"), Mock(url="https://b")]
        bot.get_subscriptions = AsyncMock(
            return_value=Mock(subscriptions=subs)
        )

        caplog.set_level("WARNING")
        await dispatcher._check_subscriptions(bot)

        warns = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warns, "Ожидалось предупреждение при найденных подписках"

        # Проверяем текст предупреждения и наличие URL'ов
        assert any("БОТ ИГНОРИРУЕТ POLLING!" in r.getMessage() for r in warns)
        joined = ", ".join([s.url for s in subs])
        assert any(joined in r.getMessage() for r in warns)


class TestDispatcherReady:
    async def test_ready_triggers_subscriptions_and_prepare_and_on_started(
        self, dispatcher, bot
    ):
        """Если включён polling и auto_check_subscriptions,
        вызываются проверки подписок, check_me, prepare и on_started.
        """
        dispatcher.polling = True
        bot.auto_check_subscriptions = True

        # Подменяем методы, чтобы отследить вызовы
        dispatcher._check_subscriptions = AsyncMock()
        dispatcher.check_me = AsyncMock()
        dispatcher._prepare_handlers = Mock()
        dispatcher.on_started_func = AsyncMock()

        # Вызов приватного метода __ready
        await dispatcher._Dispatcher__ready(bot)

        # Убедимся, что бот присвоен и бот знает диспетчера
        assert dispatcher.bot is bot
        assert bot.dispatcher is dispatcher

        # Проверяем, что были вызваны ожидаемые методы
        dispatcher._check_subscriptions.assert_called()
        dispatcher.check_me.assert_called()
        dispatcher._prepare_handlers.assert_called_once_with(bot)
        dispatcher.on_started_func.assert_called()

        # Dispatcher должен добавить себя в список роутеров
        assert dispatcher in dispatcher.routers

    async def test_ready_skips_subscriptions_when_polling_disabled(
        self, dispatcher, bot
    ):
        """Если polling отключён, проверка подписок не выполняется."""
        dispatcher.polling = False
        bot.auto_check_subscriptions = True

        dispatcher._check_subscriptions = AsyncMock()
        dispatcher.check_me = AsyncMock()
        dispatcher._prepare_handlers = Mock()
        dispatcher.on_started_func = None

        await dispatcher._Dispatcher__ready(bot)

        # _check_subscriptions не должен вызываться
        dispatcher._check_subscriptions.assert_not_called()

        # Остальные шаги должны выполниться
        dispatcher.check_me.assert_called()
        dispatcher._prepare_handlers.assert_called_once_with(bot)
        assert dispatcher in dispatcher.routers
