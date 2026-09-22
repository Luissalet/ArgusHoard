from argus.exclusions import Rule, first_match, is_excluded, validate_pattern


RULES = [
    Rule(1, "app", "banco-app"),
    Rule(2, "app", "Keepass*"),
    Rule(3, "title", r"\bincógnito\b|private browsing"),
    Rule(4, "title", "secreto", enabled=False),
]


def test_app_rules_ignore_case_and_exe_suffix():
    assert is_excluded(RULES, "Banco-App.exe", "")
    assert is_excluded(RULES, "keepassxc", "")
    assert not is_excluded(RULES, "notepad", "banco-app")  # app rules never look at titles


def test_title_rules_are_regex_case_insensitive():
    assert first_match(RULES, "chrome", "Noticias - Navegación de INCÓGNITO").id == 3
    assert is_excluded(RULES, "firefox", "Mozilla Firefox Private Browsing")
    assert not is_excluded(RULES, "chrome", "Noticias del día")


def test_disabled_rules_do_not_match():
    assert not is_excluded(RULES, "editor", "documento secreto")


def test_validate_pattern():
    assert validate_pattern("title", "[unclosed") is not None
    assert validate_pattern("app", "") is not None
    assert validate_pattern("other", "x") is not None
    assert validate_pattern("title", r"\d+ facturas") is None
