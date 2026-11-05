import pytest
from aiogram.types import MessageEntity

from bot.links import channel_post_url, extract_urls, post_title


def entity(type_, offset=0, length=0, url=None):
    return MessageEntity(type=type_, offset=offset, length=length, url=url)


def test_plain_url_entity():
    text = "смотри https://example.com/a сегодня"
    start = len("смотри ")
    entities = [entity("url", start, len("https://example.com/a"))]
    assert extract_urls(text, entities) == ["https://example.com/a"]


def test_text_link_uses_hidden_url():
    entities = [entity("text_link", 0, 3, url="https://example.com/hidden")]
    assert extract_urls("вот", entities) == ["https://example.com/hidden"]


def test_offsets_are_utf16_units():
    # эмодзи занимает 2 единицы UTF-16, поэтому ссылка начинается с позиции 10
    text = "😀 смотри example.com/x"
    assert extract_urls(text, [entity("url", 10, 13)]) == ["example.com/x"]


def test_duplicates_removed_and_order_kept():
    text = "a.com/1 b.com/2 a.com/1"
    entities = [entity("url", 0, 7), entity("url", 8, 7), entity("url", 16, 7)]
    assert extract_urls(text, entities) == ["a.com/1", "b.com/2"]


def test_no_text_or_entities():
    assert extract_urls(None, None) == []
    assert extract_urls("текст", None) == []
    assert extract_urls("текст", []) == []


def test_other_entity_types_ignored():
    entities = [entity("bold", 0, 2), entity("mention", 3, 5), entity("email", 9, 6)]
    assert extract_urls("hi @user a@b.co", entities) == []


def test_channel_post_url():
    assert channel_post_url("durov", 123) == "https://t.me/durov/123"
    assert channel_post_url("My_Channel_1", 5) == "https://t.me/My_Channel_1/5"


@pytest.mark.parametrize(
    "username",
    [None, "", "ab", "1channel", "bad name", "x/../evil", "a" * 40, "канал_имя"],
)
def test_channel_post_url_rejects_bad_username(username):
    assert channel_post_url(username, 1) is None


@pytest.mark.parametrize("message_id", [None, 0, -5])
def test_channel_post_url_rejects_bad_message_id(message_id):
    assert channel_post_url("durov", message_id) is None


def test_post_title_uses_first_nonempty_line():
    assert post_title("\n\n  Заголовок поста \nвторая строка", "durov") == "Заголовок поста"


def test_post_title_fallback_without_text():
    assert post_title(None, "durov") == "Пост из @durov"
    assert post_title("  \n ", "durov") == "Пост из @durov"


def test_post_title_is_truncated():
    assert len(post_title("a" * 500, "durov")) == 100