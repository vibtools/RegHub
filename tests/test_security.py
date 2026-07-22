from app.core.security import (
    AdminIdentity,
    AdminTokenSigner,
    derive_secret,
    sanitize_relative_redirect,
)


def test_admin_token_roundtrip() -> None:
    signer = AdminTokenSigner("x" * 64)
    token = signer.issue(
        AdminIdentity(
            "sub-1",
            "a@example.com",
            "Admin",
            {},
            ("super_admin",),
        )
    )
    identity = signer.verify(token, max_age=60)
    assert identity is not None
    assert identity.subject == "sub-1"


def test_redirect_is_local_only() -> None:
    assert sanitize_relative_redirect("/admin/templates") == "/admin/templates"
    assert sanitize_relative_redirect("//evil.example") == "/admin"
    assert sanitize_relative_redirect("https://evil.example") == "/admin"


def test_security_boundaries_use_separate_derived_keys() -> None:
    secret = "s" * 64
    assert derive_secret(secret, "admin-auth-cookie") != derive_secret(secret, "oidc-state-session")
    assert derive_secret(secret, "admin-auth-cookie") != derive_secret(
        secret, "sqladmin-aux-session"
    )


def test_redirect_rejects_backslashes_and_control_characters() -> None:
    assert sanitize_relative_redirect("/admin\\evil") == "/admin"
    assert sanitize_relative_redirect("/admin\nnext") == "/admin"
