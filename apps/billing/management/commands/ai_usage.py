"""
ai_usage — how much AI has been used, and roughly what it cost.

    docker compose exec web python manage.py ai_usage
    docker compose exec web python manage.py ai_usage --days 7
    docker compose exec web python manage.py ai_usage --tenant scale --by model
    docker compose exec web python manage.py ai_usage --json

Every LLM call already writes a TokenLedger row through the gateway. This reads that
meter back: calls, prompt/completion tokens, and an ESTIMATED cost from the price table
in ``settings.LLM_PRICES`` (USD per million tokens, overridable with LLM_PRICES_JSON).

The estimate is labelled an estimate everywhere it appears. Published prices move, free
tiers and discounts are invisible from here, and only the provider's invoice is
authoritative — a confident total from a table in a repo would be a made-up number.

Usage is recorded per TENANT, AGENT and MODEL. It is NOT recorded per user: the ledger
has no user column, so "who spent this" cannot be answered without a migration. Said
here rather than left for somebody to discover from an empty column.
"""
from django.core.management.base import BaseCommand

from apps.billing.usage import collect


def _fmt_usd(amount: float) -> str:
    return f"${amount:,.4f}" if amount < 1 else f"${amount:,.2f}"


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


class Command(BaseCommand):
    help = ("AI usage and estimated cost from the TokenLedger, over a recent window. "
            "Grouped by tenant/agent/model; cost is an estimate from settings.LLM_PRICES.")

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30,
                            help="How far back to look (default 30).")
        parser.add_argument("--tenant", default="",
                            help="Limit to one tenant slug (default: all tenants).")
        parser.add_argument("--by", default="agent_code",
                            choices=["agent_code", "model", "tenant"],
                            help="Roll the summary up by this (default agent_code).")
        parser.add_argument("--json", action="store_true",
                            help="Machine-readable output instead of a table.")

    def handle(self, *args, **options):
        usage = collect(days=options["days"], tenant_slug=options["tenant"])

        if options["json"]:
            import json

            self.stdout.write(json.dumps({
                "days": usage.days,
                "since": usage.since.isoformat(),
                "calls": usage.calls,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "estimated_cost_usd": round(usage.cost_usd, 6),
                "unpriced_models": usage.unpriced_models,
                "rows": [{
                    "tenant": r.tenant, "agent": r.agent_code, "model": r.model,
                    "calls": r.calls, "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "estimated_cost_usd": round(r.cost_usd, 6), "priced": r.priced,
                } for r in usage.rows],
            }, indent=2))
            return

        if not usage.rows:
            self.stdout.write(
                f"No AI usage recorded in the last {usage.days} day(s)"
                + (f" for tenant {options['tenant']!r}" if options["tenant"] else "")
                + ".")
            return

        title = f"AI USAGE — last {usage.days} day(s), since {usage.since:%Y-%m-%d %H:%M}"
        self.stdout.write("\n" + title)
        self.stdout.write("=" * len(title))

        key = options["by"]
        label = {"agent_code": "agent", "model": "model", "tenant": "tenant"}[key]
        width = max([len(label)] + [len(str(k)) for k, _ in usage.by(key)]) + 2
        self.stdout.write(f"  {label.ljust(width)}{'calls':>8}{'tokens':>12}{'est. cost':>14}")
        self.stdout.write("  " + "-" * (width + 34))
        for name, (calls, tokens, cost) in usage.by(key):
            self.stdout.write(
                f"  {str(name).ljust(width)}{calls:>8}{_fmt_tokens(tokens):>12}"
                f"{_fmt_usd(cost):>14}")

        self.stdout.write("  " + "-" * (width + 34))
        self.stdout.write(
            f"  {'TOTAL'.ljust(width)}{usage.calls:>8}"
            f"{_fmt_tokens(usage.total_tokens):>12}{_fmt_usd(usage.cost_usd):>14}")
        self.stdout.write(
            f"\n  in {_fmt_tokens(usage.prompt_tokens)} · "
            f"out {_fmt_tokens(usage.completion_tokens)}")
        self.stdout.write(
            "  Cost is an ESTIMATE from settings.LLM_PRICES (USD per million tokens). "
            "Only the provider's invoice is authoritative.")
        if usage.unpriced_models:
            self.stdout.write(self.style.WARNING(
                "  ! no price known for: " + ", ".join(usage.unpriced_models)
                + " — their usage is counted but costs nothing in this total."))
        self.stdout.write(
            "  Usage is recorded per tenant/agent/model. The ledger has no user column, "
            "so per-user spend is not available.\n")
