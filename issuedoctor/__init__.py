from flask import Flask

from issuedoctor.capabilities import capability_report
from issuedoctor.config import Config
from issuedoctor.extensions import csrf, db, migrate
from issuedoctor.i18n.loader import register_i18n
from issuedoctor.logging_config import configure_logging
from issuedoctor.models import AppSetting
from issuedoctor.security.secrets import build_secret_store
from issuedoctor.tasks.manager import TaskManager
from issuedoctor.tasks.recovery import recover_interrupted_runs
from issuedoctor.web.api_analysis import analysis_api_bp
from issuedoctor.web.api_assistant import assistant_api_bp
from issuedoctor.web.api_capabilities import capabilities_api_bp
from issuedoctor.web.api_governance import governance_api_bp
from issuedoctor.web.api_preflight import preflight_api_bp
from issuedoctor.web.api_settings import settings_api_bp
from issuedoctor.web.errors import register_error_handlers
from issuedoctor.web.routes_analysis import analysis_bp
from issuedoctor.web.routes_export import export_bp
from issuedoctor.web.routes_governance import governance_bp
from issuedoctor.web.routes_main import main_bp
from issuedoctor.web.routes_preflight import preflight_bp
from issuedoctor.web.routes_settings import settings_bp


def create_app(config_object: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    Config.ensure_runtime_directories(app.config)
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    register_i18n(app)
    configure_logging(app.logger)
    app.extensions["issuedoctor_secrets"] = build_secret_store(app.config)
    app.extensions["issuedoctor_tasks"] = TaskManager(
        app,
        max_workers=app.config["TASK_MAX_WORKERS"],
    )
    app.register_blueprint(main_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(settings_api_bp)
    app.register_blueprint(capabilities_api_bp)
    app.register_blueprint(preflight_bp)
    app.register_blueprint(preflight_api_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(analysis_api_bp)
    app.register_blueprint(assistant_api_bp)
    app.register_blueprint(governance_bp)
    app.register_blueprint(governance_api_bp)
    app.register_blueprint(export_bp)
    register_error_handlers(app)
    recover_interrupted_runs(app)

    for status in capability_report():
        if not status["available"]:
            app.logger.info(
                "可选能力未启用：%s（缺少 %s）",
                status["label"],
                "、".join(status["missing"]),
            )

    return app


__all__ = ["create_app", "AppSetting"]
