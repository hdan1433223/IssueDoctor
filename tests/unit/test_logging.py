import logging

from issuedoctor.logging_config import SecretRedactionFilter


def test_logging_filter_redacts_message_and_arguments():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request %s",
        args=("Authorization: Bearer top-secret",),
        exc_info=None,
    )

    assert SecretRedactionFilter().filter(record) is True
    assert "top-secret" not in record.getMessage()

