"""
Org-chart READ services + the cache.

The hierarchy is computed from the live identity graph (``User.manager``, active
users only — the scoped manager already hides soft-deleted rows, and we filter
``is_active=True`` explicitly because deactivated users must not appear in the
tree or its rollups). The EXPENSIVE part — assembling the full tenant tree with
headcount + vacancy rollups — is cached once per tenant under a tenant-scoped key
(``tenant:<id>:org:tree``); per-actor SCOPE filtering is then a pure in-memory
operation over the cached structure, so one cache entry correctly serves every
scope (OWN / TEAM / TENANT) without a per-manager key explosion. The cache is
invalidated (whole ``org`` namespace) by every consequential write — a position
create/fill/close/JD-link or a reporting-line reassignment — so a read
immediately after a write reflects the change.

Scope (decision 2, mirrors ``apps.rbac.scope``):
  * Employee (OWN)    -> own node + ancestor chain to the root (their line).
  * Manager  (TEAM)   -> own reporting subtree + self + ancestor chain.
  * HRBP/Admin(TENANT)-> the whole tenant tree (multiple roots allowed).

Person-card / search / export are scope-bounded the same way; an out-of-scope
target is a 404 (never a 403 that leaks existence), matching the Module-6 rule.
"""
from __future__ import annotations

from django.core.cache import cache
from rest_framework.exceptions import NotFound

from apps.core.cache import invalidate_tenant_cache, tenant_cache_key
from apps.identity.models import User
from apps.rbac.scope import Scope, actor_can_access, scope_for_role
from apps.tenancy.context import tenant_context

from .models import Position

#: Cache key parts + TTL for the assembled full-tenant tree.
_ORG_NAMESPACE = "org"
_ORG_TREE_PART = (_ORG_NAMESPACE, "tree")
_ORG_TREE_TTL = 600


def _tenant_id(value) -> str:
    return str(getattr(value, "id", value))


# ── cache ────────────────────────────────────────────────────────────────────


def invalidate_org_cache(tenant) -> None:
    """Drop the tenant's cached org tree (the whole ``org`` namespace). Called by
    every write that can change the tree, the rollups, or a vacancy."""
    invalidate_tenant_cache(_tenant_id(tenant), _ORG_NAMESPACE)


def get_full_tree(tenant) -> dict:
    """Return the cached full-tenant tree (compute + cache on miss).

    The single DB-touching read; everything user-facing filters this in memory.
    """
    tid = _tenant_id(tenant)
    key = tenant_cache_key(tid, *_ORG_TREE_PART)
    cached = cache.get(key)
    if cached is not None:
        return cached
    tree = _compute_full_tree(tid)
    cache.set(key, tree, _ORG_TREE_TTL)
    return tree


def _compute_full_tree(tenant_id) -> dict:
    """Assemble the full tenant tree with headcount + vacancy rollups.

    Active users only. JSON-safe payload (all ids are strings) so it pickles into
    the cache cleanly. ``headcount`` = active users in the node's subtree
    (inclusive); ``vacancies`` = OPEN positions whose ``reports_to`` is anywhere
    in the node's subtree (inclusive)."""
    with tenant_context(tenant_id):
        rows = list(
            User.objects.filter(is_active=True).values(
                "id", "email", "role", "manager_id", "display_name"
            )
        )
        open_positions = list(
            Position.objects.filter(status=Position.Status.OPEN).values_list(
                "reports_to_id", flat=True
            )
        )

    ids = {str(r["id"]) for r in rows}
    children: dict[str, list[str]] = {i: [] for i in ids}
    roots: list[str] = []
    for r in rows:
        mid = str(r["manager_id"]) if r["manager_id"] else None
        # A manager outside the active set (e.g. deactivated) makes this a root.
        if mid and mid in ids:
            children[mid].append(str(r["id"]))
        else:
            roots.append(str(r["id"]))

    direct_vac: dict[str, int] = {}
    for rid in open_positions:
        if rid is None:
            continue
        rid = str(rid)
        if rid in ids:
            direct_vac[rid] = direct_vac.get(rid, 0) + 1

    headcount, vacancy = _rollups(children, direct_vac, ids)

    nodes = {}
    for r in rows:
        nid = str(r["id"])
        mid = str(r["manager_id"]) if r["manager_id"] else None
        nodes[nid] = {
            "id": nid,
            "email": r["email"],
            # Effective display name (mirrors User.display: display_name or email)
            # so the org chart renders names, never bare emails/uuids.
            "display": r["display_name"] or r["email"],
            "role": r["role"],
            "manager_id": mid if (mid in ids) else None,
            "direct_report_ids": sorted(children.get(nid, [])),
            "headcount": headcount.get(nid, 1),
            "vacancies": vacancy.get(nid, 0),
        }
    return {"nodes": nodes, "roots": sorted(roots)}


def _rollups(children, direct_vac, all_ids):
    """Post-order subtree rollups with a cycle guard (a corrupt loop terminates
    rather than spinning — real cycles are prevented by ``reassign``)."""
    headcount: dict[str, int] = {}
    vacancy: dict[str, int] = {}
    visiting: set[str] = set()

    def visit(nid):
        if nid in headcount:
            return
        if nid in visiting:  # cycle guard: treat as a leaf
            headcount[nid] = 1
            vacancy[nid] = direct_vac.get(nid, 0)
            return
        visiting.add(nid)
        hc = 1
        vc = direct_vac.get(nid, 0)
        for child in children.get(nid, ()):  # noqa: B007
            visit(child)
            hc += headcount[child]
            vc += vacancy[child]
        headcount[nid] = hc
        vacancy[nid] = vc
        visiting.discard(nid)

    for nid in all_ids:
        visit(nid)
    return headcount, vacancy


# ── scope helpers (pure, over the cached tree) ────────────────────────────────


def _ancestor_ids(node_id, nodes) -> set[str]:
    """The chain of managers above ``node_id`` (exclusive), walked over the cached
    node map with a cycle guard."""
    chain: set[str] = set()
    current = nodes.get(node_id, {}).get("manager_id")
    while current and current in nodes and current not in chain:
        chain.add(current)
        current = nodes[current]["manager_id"]
    return chain


def _descendant_ids(node_id, nodes) -> set[str]:
    """Every transitive report beneath ``node_id`` (exclusive), over the cached
    node map with a cycle guard."""
    seen: set[str] = set()
    frontier = list(nodes.get(node_id, {}).get("direct_report_ids", []))
    while frontier:
        cur = frontier.pop()
        if cur in seen or cur not in nodes:
            continue
        seen.add(cur)
        frontier.extend(nodes[cur]["direct_report_ids"])
    return seen


def _visible_ids(actor, tree) -> set[str]:
    """The set of node ids ``actor`` may see, per the §2 scope tier — computed
    purely from the cached tree (no DB)."""
    nodes = tree["nodes"]
    aid = str(actor.id)
    scope = scope_for_role(actor.role)
    if scope is Scope.TENANT:
        return set(nodes)
    if aid not in nodes:
        return {aid}
    if scope is Scope.OWN:
        return {aid} | _ancestor_ids(aid, nodes)
    # TEAM: self + reporting subtree + ancestor chain (for context).
    return {aid} | _descendant_ids(aid, nodes) | _ancestor_ids(aid, nodes)


# ── public reads ──────────────────────────────────────────────────────────────


def build_org_tree(actor) -> dict:
    """The scoped org tree for ``actor``: ``{nodes, edges, roots}``.

    ``roots`` are the topmost VISIBLE nodes (a node whose manager is not itself
    visible is a root of the returned subgraph). Edges connect a visible manager
    to a visible report.
    """
    tree = get_full_tree(actor.tenant_id)
    all_nodes = tree["nodes"]
    visible = _visible_ids(actor, tree) & set(all_nodes)

    nodes = [all_nodes[i] for i in sorted(visible)]
    edges = [
        {"from": n["manager_id"], "to": n["id"]}
        for n in nodes
        if n["manager_id"] in visible
    ]
    roots = sorted(n["id"] for n in nodes if n["manager_id"] not in visible)
    return {"nodes": nodes, "edges": edges, "roots": roots}


def person_card(actor, user_id) -> dict:
    """Scoped detail for one person. Out-of-scope (or inactive / cross-tenant) is
    a 404, never a 403 that would leak existence."""
    # select_related the manager FK — the card resolves target.manager below, so
    # fetch it in the same query instead of a second round-trip.
    target = User.objects.select_related("manager").filter(id=user_id, is_active=True).first()
    if target is None or not actor_can_access(actor, target):
        raise NotFound("No such person in your org view.")

    direct_reports = User.objects.filter(manager_id=target.id, is_active=True).count()
    filled = list(
        Position.objects.filter(filled_by_id=target.id, status=Position.Status.FILLED)
    )
    title = filled[0].title if filled else None
    published_jd_ids = sorted(
        {str(p.published_jd_id) for p in filled if p.published_jd_id}
    )
    manager = target.manager if (target.manager_id and target.manager.is_active) else None
    return {
        "id": str(target.id),
        "email": target.email,
        "display_name": target.display_name,   # raw (may be null) — for editing
        "display": target.display,             # effective name (falls back to email)
        "role": target.role,
        "title": title,
        "manager": (
            {"id": str(manager.id), "email": manager.email, "display": manager.display}
            if manager else None
        ),
        "direct_reports": direct_reports,
        "filled_positions": [
            {
                "id": str(p.id),
                "title": p.title,
                "department": p.department,
                "published_jd": str(p.published_jd_id) if p.published_jd_id else None,
            }
            for p in filled
        ],
        "published_jds": published_jd_ids,
    }


def search_people(actor, query) -> list[dict]:
    """People within ``actor``'s scope whose email OR filled-position title
    matches ``query`` (case-insensitive)."""
    tree = get_full_tree(actor.tenant_id)
    visible = _visible_ids(actor, tree) & set(tree["nodes"])
    if not query:
        matched = set(visible)
    else:
        by_email = set(
            str(i)
            for i in User.objects.filter(
                is_active=True, id__in=visible, email__icontains=query
            ).values_list("id", flat=True)
        )
        by_title = set(
            str(i)
            for i in Position.objects.filter(
                status=Position.Status.FILLED,
                title__icontains=query,
                filled_by_id__in=visible,
            ).values_list("filled_by_id", flat=True)
        )
        matched = by_email | by_title
    nodes = tree["nodes"]
    title_by_user = _titles_for(matched)
    # Effective display name per matched user (display_name or email fallback).
    display_by_user = {
        str(u.id): (u.display_name, u.display)
        for u in User.objects.filter(id__in=[n for n in matched if n in nodes])
    }
    return [
        {
            "id": nid,
            "email": nodes[nid]["email"],
            "display_name": display_by_user.get(nid, (None, nodes[nid]["email"]))[0],
            "display": display_by_user.get(nid, (None, nodes[nid]["email"]))[1],
            "role": nodes[nid]["role"],
            "title": title_by_user.get(nid),
        }
        for nid in sorted(matched)
        if nid in nodes
    ]


def _titles_for(user_ids) -> dict[str, str]:
    """Map user id -> their filled-position title (if any), for a set of ids."""
    if not user_ids:
        return {}
    rows = Position.objects.filter(
        status=Position.Status.FILLED, filled_by_id__in=user_ids
    ).values_list("filled_by_id", "title")
    out: dict[str, str] = {}
    for uid, title in rows:
        out.setdefault(str(uid), title)
    return out


def list_vacancies(actor) -> list[dict]:
    """OPEN positions (vacancies) within ``actor``'s scope. FILLED/CLOSED never
    count. HRBP/Admin (TENANT) also see tenant-level vacancies (reports_to null);
    Manager/Employee see only vacancies reporting into their visible subtree."""
    tree = get_full_tree(actor.tenant_id)
    visible = _visible_ids(actor, tree) & set(tree["nodes"])
    positions = Position.objects.filter(status=Position.Status.OPEN).select_related(
        "reports_to"
    )
    if scope_for_role(actor.role) is not Scope.TENANT:
        positions = positions.filter(reports_to_id__in=visible)
    return [_vacancy_dict(p) for p in positions]


def _vacancy_dict(position) -> dict:
    rt = position.reports_to if position.reports_to_id else None
    return {
        "id": str(position.id),
        "title": position.title,
        "department": position.department,
        "status": position.status,
        "reports_to": ({"id": str(rt.id), "email": rt.email} if rt else None),
        "published_jd": str(position.published_jd_id) if position.published_jd_id else None,
        "opened_at": position.opened_at.isoformat() if position.opened_at else None,
    }


def export_org(actor) -> dict:
    """The scoped org structure as structured JSON + a flat node list (text/JSON
    only; no binary export)."""
    tree = build_org_tree(actor)
    return {
        "tree": tree,
        "flat": tree["nodes"],
        "node_count": len(tree["nodes"]),
        "scope": scope_for_role(actor.role).value,
    }
