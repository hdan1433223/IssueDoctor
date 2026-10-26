from issuedoctor.extensions import db


def test_home_page_is_accessible(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "IssueDoctor" in response.get_data(as_text=True)
    assert "开始预检" in response.get_data(as_text=True)
    assert "psf/requests" in response.get_data(as_text=True)
    assert "六个维度分别在看什么" in response.get_data(as_text=True)


def test_guide_explains_workflow_metrics_and_free_ai(client):
    response = client.get("/guide")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "从填写仓库到落地治理" in body
    assert "首次维护者响应中位时间" in body
    assert "https://api.groq.com/openai/v1" in body
    assert "openrouter/free" in body


def test_health_check(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_database_schema_can_be_created(app):
    with app.app_context():
        db.create_all()
        table_names = set(db.inspect(db.engine).get_table_names())

    assert "app_settings" in table_names
