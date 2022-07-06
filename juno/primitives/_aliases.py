# We need this module because defining an alias and using it within the same module does not work.
# It drives `mypy` crazy and says that the type is not allowed.

from typing import _GenericAlias  # type: ignore

Interval = _GenericAlias(int, (), name="Interval")

# Note that we alias `Interval` instead of `int`. This is required because typing module seems to
# erase duplicate aliases to same type. If `Timestamp` also aliased `int`, `Optional[Interval]`
# would be resolved as `Union[Timestamp, None]` instead.
Timestamp = _GenericAlias(Interval, (), name="Timestamp")

Asset = _GenericAlias(str, (), name="Asset")

# Similar reason for using `Asset` here as was for `Timestamp`.
Symbol = _GenericAlias(Asset, (), name="Symbol")
