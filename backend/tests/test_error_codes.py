from app.error_messages import ERROR_MESSAGES


def test_error_code_registry_has_core_entries():
    assert "UNAUTHORIZED" in ERROR_MESSAGES
    assert "FEDERATION_REPLAY" in ERROR_MESSAGES
    assert "INTERNAL_ERROR" in ERROR_MESSAGES


def test_error_messages_are_non_empty():
    for code, message in ERROR_MESSAGES.items():
        assert isinstance(code, str)
        assert isinstance(message, str)
        assert code.strip() != ""
        assert message.strip() != ""
