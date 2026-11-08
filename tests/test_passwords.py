from argon2 import PasswordHasher

from app.passwords import hash_password, needs_rehash, verify_dummy, verify_password


def test_hash_is_argon2id_and_salted():
    first = hash_password("correct horse battery")
    second = hash_password("correct horse battery")
    assert first.startswith("$argon2id$")
    assert first != second  # соль разная
    assert "correct horse" not in first


def test_verify_correct_and_wrong_password():
    stored = hash_password("correct horse battery")
    assert verify_password("correct horse battery", stored) is True
    assert verify_password("wrong horse battery", stored) is False


def test_unicode_password():
    stored = hash_password("пароль-из-кириллицы")
    assert verify_password("пароль-из-кириллицы", stored) is True


def test_garbage_hash_is_rejected_not_raised():
    assert verify_password("anything", "not-a-hash") is False
    assert verify_password("anything", "") is False


def test_fresh_hash_does_not_need_rehash():
    assert needs_rehash(hash_password("correct horse battery")) is False


def test_weaker_hash_needs_rehash():
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("x" * 12)
    assert needs_rehash(weak) is True


def test_dummy_verification_runs_without_result():
    assert verify_dummy("anything") is None