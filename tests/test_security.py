from app.core.security import AdminIdentity, AdminTokenSigner, sanitize_relative_redirect


def test_admin_token_roundtrip() -> None:
    signer = AdminTokenSigner("x" * 64)
    token = signer.issue(AdminIdentity("sub-1", "a@example.com", "Admin", {"roles": ["admin"]}))
    identity = signer.verify(token, max_age=60)
    assert identity is not None
    assert identity.subject == "sub-1"


def test_redirect_is_local_only() -> None:
    assert sanitize_relative_redirect("/admin/templates") == "/admin/templates"
    assert sanitize_relative_redirect("//evil.example") == "/admin"
    assert sanitize_relative_redirect("https://evil.example") == "/admin"
