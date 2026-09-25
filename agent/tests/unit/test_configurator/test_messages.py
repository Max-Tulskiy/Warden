"""Everything the connection window and its command line show is Russian (R-17)."""

import re

from warden_agent.configurator import messages

CYRILLIC = re.compile("[А-Яа-яЁё]")


def _texts() -> dict[str, str]:
    return {
        name: value
        for name, value in vars(messages).items()
        if name.isupper() and isinstance(value, str)
    }


def test_the_catalog_is_not_empty():
    assert len(_texts()) > 10


def test_every_text_in_the_catalog_is_russian():
    latin_only = [name for name, text in _texts().items() if not CYRILLIC.search(text)]

    assert latin_only == []


def test_the_texts_that_take_values_fill_them_in():
    for name, text in _texts().items():
        placeholders = re.findall(r"{(\w+)}", text)
        if placeholders:
            filled = text.format(**dict.fromkeys(placeholders, "значение"))
            assert "{" not in filled, name
