from apps.accounts.domain.names import normalize_full_name


def test_trims_and_collapses_inner_whitespace():
    assert normalize_full_name("  Zainab   Khan  ") == "Zainab Khan"


def test_leaves_a_clean_name_unchanged():
    assert normalize_full_name("Bilal Raza") == "Bilal Raza"
