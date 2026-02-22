"""Тесты для утилит, связанных с командами бота."""

from maxapi.bot import Bot
from maxapi.enums.update import UpdateType
from maxapi.filters.command import Command, CommandsInfo
from maxapi.filters.filter import BaseFilter
from maxapi.filters.handler import Handler
from maxapi.utils.commands import extract_commands, get_handler_info


class TestGetHandlerInfo:
    @staticmethod
    def make_handler(doc: str | None) -> Handler:
        def func(): ...

        func.__doc__ = doc
        return Handler(func_event=func, update_type=UpdateType.ON_STARTED)

    def test_no_doc_returns_none(self):
        handler = self.make_handler(None)
        assert get_handler_info(handler) is None

    def test_doc_without_pattern_returns_none(self):
        doc = """
        This handler does something useful.
        No commands info here.
        """
        handler = self.make_handler(doc)
        assert get_handler_info(handler) is None

    def test_single_line_commands_info(self):
        doc = """
        Handler description
        \n
        commands_info: Запустить бота и показать приветствие
        """
        handler = self.make_handler(doc)
        assert (
            get_handler_info(handler)
            == "Запустить бота и показать приветствие"
        )

    def test_commands_info_stops_at_newline(self):
        doc = """
        Handler description

        commands_info: Первая строка\nВторая строка с подробностями
        """
        handler = self.make_handler(doc)
        assert get_handler_info(handler) == "Первая строка"

    def test_commands_info_with_trailing_spaces(self):
        doc = """
        commands_info:    Описание с пробелами    \n
        Дополнительный текст
        """
        handler = self.make_handler(doc)
        assert get_handler_info(handler) == "Описание с пробелами"

    def test_commands_info_label_at_end_returns_none(self):
        doc = """
        Some text
        commands_info:
        """
        handler = self.make_handler(doc)

        # Проверяем, что если после "commands_info:" нет текста,
        # возвращается None, т.к. нет полезной информации
        assert get_handler_info(handler) is None


class TestExtractCommands:
    @staticmethod
    def make_handler(*base_filters, doc: str | None = None) -> Handler:
        def func(): ...

        func.__doc__ = doc
        return Handler(
            *base_filters,
            func_event=func,
            update_type=UpdateType.ON_STARTED,
        )

    def test_extract_commands_with_no_base_filters(self):
        bot = Bot(token="test")
        handler = self.make_handler()

        extract_commands(handler, bot)

        assert bot.commands == []

    def test_extract_commands_with_base_filter_without_commands(self):
        bot = Bot(token="test")
        base = BaseFilter()
        handler = self.make_handler(base)

        extract_commands(handler, bot)

        assert bot.commands == []

    def test_extract_commands_with_command_and_info(self):
        bot = Bot(token="test")
        doc = """
        Some handler

        commands_info: Описание команды
        """
        cmd = Command("start")
        handler = self.make_handler(cmd, doc=doc)

        extract_commands(handler, bot)

        assert bot.commands == [
            CommandsInfo(commands=["start"], info="Описание команды")
        ]

    def test_extract_commands_multiple_base_filters_and_info(self):
        bot = Bot(token="test")
        doc = """
        commands_info: Общая инфа
        """
        cmd1 = Command("a")
        cmd2 = Command(["b", "c"])
        handler = self.make_handler(cmd1, cmd2, doc=doc)

        extract_commands(handler, bot)

        assert bot.commands == [
            CommandsInfo(commands=["a"], info="Общая инфа"),
            CommandsInfo(commands=["b", "c"], info="Общая инфа"),
        ]

    def test_extract_commands_handler_base_filters_none_is_noop(self):
        bot = Bot(token="test")
        handler = self.make_handler()

        # симулируем необычное состояние, когда base_filters равно None
        handler.base_filters = None

        extract_commands(handler, bot)

        assert bot.commands == []
