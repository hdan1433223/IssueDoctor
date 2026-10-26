"""Read-only endpoints describing optional capabilities and plugins.

The UI uses these to explain what is available in the current installation and
how to enable anything that is not, instead of failing silently.
"""

from flask import Blueprint, jsonify

from issuedoctor.capabilities import capability_report
from issuedoctor.plugins import summary as plugin_summary

capabilities_api_bp = Blueprint("capabilities_api", __name__, url_prefix="/api/capabilities")


@capabilities_api_bp.get("")
def get_capabilities():
    return jsonify(
        {
            "ok": True,
            "core": {
                "label": "核心诊断",
                "available": True,
                "description": "GitHub 采集、六维确定性评分、报告导出、Web 界面",
            },
            "capabilities": capability_report(),
            "plugins": plugin_summary(),
        }
    )
