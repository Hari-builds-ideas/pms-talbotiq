"""Auth-flow side effects that aren't token minting."""


def establish_session(request, user):
    """Write a fresh server-side session for the authenticated user.

    The session store is the Redis cache (``SESSION_ENGINE = cache``) in
    dev/prod, so this satisfies the Module 1 login workflow's "write session to
    Redis" step. Returns the new session key.
    """
    request.session.flush()
    request.session["user_id"] = str(user.id)
    request.session["tenant_id"] = str(user.tenant_id)
    request.session["role"] = user.role
    request.session.save()
    return request.session.session_key
