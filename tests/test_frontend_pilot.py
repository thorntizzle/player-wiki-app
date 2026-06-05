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

    account_route_response = client.get("/app-next/account")
    assert account_route_response.status_code == 200
    assert account_route_response.data == response.data

    help_route_response = client.get("/app-next/campaigns/linden-pass/help")
    assert help_route_response.status_code == 200
    assert help_route_response.data == response.data

    control_route_response = client.get("/app-next/campaigns/linden-pass/control")
    assert control_route_response.status_code == 200
    assert control_route_response.data == response.data

    character_route_response = client.get("/app-next/campaigns/linden-pass/characters/arden-march")
    assert character_route_response.status_code == 200
    assert character_route_response.data == response.data

    character_editor_route_response = client.get("/app-next/campaigns/linden-pass/characters/arden-march/edit")
    assert character_editor_route_response.status_code == 200
    assert character_editor_route_response.data == response.data

    character_level_up_route_response = client.get("/app-next/campaigns/linden-pass/characters/arden-march/level-up")
    assert character_level_up_route_response.status_code == 200
    assert character_level_up_route_response.data == response.data

    character_retraining_route_response = client.get("/app-next/campaigns/linden-pass/characters/arden-march/retraining")
    assert character_retraining_route_response.status_code == 200
    assert character_retraining_route_response.data == response.data

    character_progression_repair_route_response = client.get(
        "/app-next/campaigns/linden-pass/characters/arden-march/progression-repair"
    )
    assert character_progression_repair_route_response.status_code == 200
    assert character_progression_repair_route_response.data == response.data

    character_cultivation_route_response = client.get(
        "/app-next/campaigns/linden-pass/characters/arden-march/cultivation"
    )
    assert character_cultivation_route_response.status_code == 200
    assert character_cultivation_route_response.data == response.data

    combat_route_response = client.get("/app-next/campaigns/linden-pass/combat")
    assert combat_route_response.status_code == 200
    assert combat_route_response.data == response.data

    dm_content_route_response = client.get("/app-next/campaigns/linden-pass/dm-content")
    assert dm_content_route_response.status_code == 200
    assert dm_content_route_response.data == response.data

    systems_route_response = client.get("/app-next/campaigns/linden-pass/systems")
    assert systems_route_response.status_code == 200
    assert systems_route_response.data == response.data

    systems_source_route_response = client.get("/app-next/campaigns/linden-pass/systems/sources/MM")
    assert systems_source_route_response.status_code == 200
    assert systems_source_route_response.data == response.data

    systems_category_route_response = client.get("/app-next/campaigns/linden-pass/systems/sources/MM/types/monster")
    assert systems_category_route_response.status_code == 200
    assert systems_category_route_response.data == response.data

    systems_entry_route_response = client.get("/app-next/campaigns/linden-pass/systems/entries/goblin")
    assert systems_entry_route_response.status_code == 200
    assert systems_entry_route_response.data == response.data

    missing_asset_response = client.get("/app-next/assets/missing.js")
    assert missing_asset_response.status_code == 404


def test_frontend_pilot_without_build_returns_not_found(client, app, tmp_path):
    # Avoid inheriting temp values from earlier test cases.
    app.config["APP_NEXT_DIST_DIR"] = tmp_path / "missing-frontend-dist"
    response = client.get("/app-next/")
    assert response.status_code == 404
