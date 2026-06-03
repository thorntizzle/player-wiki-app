def test_frontend_pilot_routes_and_spa_fallback(client, app, tmp_path):
    dist_dir = tmp_path / "frontend-dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text("<!doctype html><html><body>pilot</body></html>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('pilot')", encoding="utf-8")

    app.config["APP_NEXT_DIST_DIR"] = dist_dir

    response = client.get("/app-next/")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert response.data == b"<!doctype html><html><body>pilot</body></html>"

    asset_response = client.get("/app-next/assets/app.js")
    assert asset_response.status_code == 200
    assert asset_response.data == b"console.log('pilot')"

    route_response = client.get("/app-next/campaigns/linden-pass/session")
    assert route_response.status_code == 200
    assert route_response.data == response.data

    missing_asset_response = client.get("/app-next/assets/missing.js")
    assert missing_asset_response.status_code == 404


def test_frontend_pilot_without_build_returns_not_found(client, app, tmp_path):
    # Avoid inheriting temp values from earlier test cases.
    app.config["APP_NEXT_DIST_DIR"] = tmp_path / "missing-frontend-dist"
    response = client.get("/app-next/")
    assert response.status_code == 404
