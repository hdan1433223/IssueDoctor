from flask import Blueprint, render_template

from issuedoctor.capabilities import capability_report
from issuedoctor.plugins import summary as plugin_summary
from issuedoctor.services.settings_service import SettingsService

settings_bp = Blueprint("settings", __name__)


@settings_bp.get("/settings")
def settings_page():
    return render_template(
        "settings.html",
        settings=SettingsService().get_public(),
        capabilities=capability_report(),
        plugins=plugin_summary(),
    )

