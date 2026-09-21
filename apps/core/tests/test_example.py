from apps.core.domain.example import add_whole_numbers


def test_add_whole_numbers_sums_two_integers():
    assert add_whole_numbers(2, 3) == 5
