from flask import Blueprint, render_template

from issuedoctor.guidance import AI_PROVIDERS, DIMENSIONS, METRICS, WORKFLOW_STEPS

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    return render_template(
        "index.html",
        recent_analyses=[],
        dimensions=DIMENSIONS,
        workflow_steps=WORKFLOW_STEPS,
    )


@main_bp.get("/guide")
def guide():
    return render_template(
        "guide.html",
        dimensions=DIMENSIONS,
        metrics=METRICS,
        workflow_steps=WORKFLOW_STEPS,
        ai_providers=AI_PROVIDERS,
    )


@main_bp.get("/healthz")
def healthz():
    return {"status": "ok"}
