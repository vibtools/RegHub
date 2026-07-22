from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_v0232_settings_repository_hotfix import _settings_app


def _csrf(page: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', page)
    assert match is not None
    return match.group(1)


def test_dedicated_settings_action_endpoint_avoids_post_route_404(tmp_path: Path) -> None:
    app, engine = _settings_app(tmp_path)
    with TestClient(app) as client:
        page = client.get("/admin/settings?tab=integrations-pane")
        assert page.status_code == 200

        response = client.post(
            "/admin/settings/action?tab=integrations-pane",
            data={
                "csrf_token": _csrf(page.text),
                "action": "reload_runtime",
                "return_tab": "integrations-pane",
            },
            headers={"X-Requested-With": "RegHub-Settings", "Accept": "text/html"},
        )

        assert response.status_code == 200
        assert "Runtime configuration reloaded." in response.text
        assert re.search(r'class="nav-link active" id="integrations-tab"', response.text)
        assert re.search(r'class="tab-pane fade show active" id="integrations-pane"', response.text)

        # The original page POST remains available as the no-JavaScript fallback.
        fallback = client.post(
            "/admin/settings?tab=integrations-pane",
            data={
                "csrf_token": _csrf(response.text),
                "action": "reload_runtime",
                "return_tab": "integrations-pane",
            },
        )
        assert fallback.status_code == 200
        assert "Runtime configuration reloaded." in fallback.text

    asyncio.run(engine.dispose())


def test_settings_ajax_replaces_only_active_pane_and_never_freezes_whole_page() -> None:
    markup = (Path(__file__).parents[1] / "templates" / "settings.html").read_text(encoding="utf-8")

    assert "new URL('/admin/settings/action'" in markup
    assert "replacePaneFromDocument" in markup
    assert "current.replaceWith(nextPane)" in markup
    assert "currentShell.replaceWith(nextShell)" not in markup
    assert "AbortController" in markup
    assert "window.setTimeout(() => controller.abort(), 45000)" in markup
    assert "setFormBusy(form, submitter, true)" in markup
    assert "document.body.contains(form)" in markup
    assert "form.closest('.tab-pane')?.id || currentPane()" in markup
    assert "document.querySelectorAll('input[name=\"return_tab\"]')" in markup
    assert "expandedIds" in markup
    assert "window.scrollTo({top: scrollTop" in markup
    assert "data-settings-server-alert" in markup
