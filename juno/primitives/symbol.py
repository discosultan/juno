from types import ModuleType

from ._aliases import Asset, Symbol


class Symbol_(ModuleType):
    @staticmethod
    def assets(symbol: Symbol) -> tuple[Asset, Asset]:
        index_of_separator = symbol.find("-")
        return symbol[:index_of_separator], symbol[index_of_separator + 1 :]

    @staticmethod
    def base_asset(symbol: Symbol) -> Asset:
        index_of_separator = symbol.find("-")
        return symbol[:index_of_separator]

    @staticmethod
    def quote_asset(symbol: Symbol) -> Asset:
        index_of_separator = symbol.find("-")
        return symbol[index_of_separator + 1 :]
