import logging

from issuedoctor.security.redaction import redact_secret


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_secret(record.msg)
        if record.args:
            record.args = redact_secret(record.args)
        return True


def configure_logging(app_logger: logging.Logger) -> None:
    for handler in app_logger.handlers:
        if not any(isinstance(item, SecretRedactionFilter) for item in handler.filters):
            handler.addFilter(SecretRedactionFilter())

