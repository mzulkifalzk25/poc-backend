from apps.accounts.domain.names import initials, normalize_full_name


def test_trims_and_collapses_inner_whitespace():
    assert normalize_full_name("  Zainab   Khan  ") == "Zainab Khan"


def test_leaves_a_clean_name_unchanged():
    assert normalize_full_name("Bilal Raza") == "Bilal Raza"


def test_initials_use_the_first_and_last_word():
    assert initials("Zainab Khan") == "ZK"
    assert initials("  hina   ali  malik ") == "HM"


def test_initials_of_a_single_word_is_one_letter():
    assert initials("Bilal") == "B"
    assert initials("") == ""
