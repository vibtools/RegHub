from app.core.security import AdminIdentity


def super_admin_identity(subject: str = "admin-user") -> AdminIdentity:
    return AdminIdentity(
        subject=subject,
        email=None,
        name="Test Administrator",
        claims={},
        roles=("super_admin",),
    )
