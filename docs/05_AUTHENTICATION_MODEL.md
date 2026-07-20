# Authentication Model

RegHub uses Authorization Code OIDC through `auth.vib.tools`. Authlib validates the authorization
response and ID token through discovery metadata. Access additionally requires an allowed value
in the configured admin claim. RegHub stores a short-lived signed HttpOnly administrator cookie.
