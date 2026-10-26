from flask import Flask, jsonify, render_template, request

from issuedoctor.errors import IssueDoctorError


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(IssueDoctorError)
    def handle_issuedoctor_error(error: IssueDoctorError):
        payload = {"ok": False, "code": error.code, "message": error.message}
        if request.path.startswith("/api/"):
            return jsonify(payload), error.status_code
        return render_template("error.html", error=payload), error.status_code

