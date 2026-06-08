import click
from dotenv import load_dotenv

from . import service
from .config import Config


@click.command()
@click.argument("query", required=False)
@click.option("--reindex", is_flag=True, help="Incrementally sync the index (embed only changed notes).")
@click.option("--rebuild", is_flag=True, help="Force a full rebuild of the index.")
@click.option("--status", "status", is_flag=True, help="Show index drift vs the vault (read-only, no embedding).")
@click.option("--no-sync", "no_sync", is_flag=True, help="Skip the auto-sync a query runs by default (faster, may be stale).")
@click.option("--mode", type=click.Choice(["vector", "fts", "hybrid"]), default=None,
              help="Search mode. Default from config (hybrid). 'fts' is offline.")
@click.option("--vault", default=None, help="Vault path override.")
@click.option("--k", default=8, help="Number of results.")
def main(query, reindex, rebuild, status, no_sync, mode, vault, k):
    load_dotenv()  # VOYAGE_API_KEY / VAULT_PATH from a .env in the project root
    cfg = Config()
    if vault:
        cfg.vault_path = vault

    did_index = False
    if rebuild:
        n = service.rebuild(cfg)
        click.echo(f"Rebuilt index: {n} chunks from {cfg.vault_path}")
        did_index = True
    elif reindex:
        r = service.sync(cfg)
        if r["full"]:
            click.echo(f"Indexed {r['chunks']} chunks from {cfg.vault_path} (full build)")
        else:
            click.echo(f"Synced: {r['new']} new, {r['changed']} changed, "
                       f"{r['deleted']} deleted, {r['chunks']} chunks embedded")
        did_index = True
    elif status:
        _status(cfg)
        return

    if not query:
        if did_index:
            return
        raise click.UsageError("Provide a QUERY, or use --reindex / --rebuild / --status.")

    if not (reindex or rebuild):  # --reindex/--rebuild already reconciled above
        if not service.has_index(cfg):
            raise click.UsageError("No index yet. Run --reindex first.")
        if not no_sync:
            synced = service.auto_sync(cfg)
            if synced and synced["reconciled"]:
                click.echo(f"(auto-synced {synced['reconciled']} change(s))", err=True)

    mode = mode or cfg.search_mode
    hits = service.search(cfg, query, k, mode)
    _print_hits(query, mode, hits)


def _status(cfg) -> None:
    _, has, new, changed, deleted = service.classify(cfg)
    if not has:
        raise click.UsageError("No index yet. Run --reindex first.")
    if not (new or changed or deleted):
        click.echo("IN SYNC")
        return
    click.echo("STALE — run --reindex")
    for n in new:
        click.echo(f"  added:   {n.note_path}")
    for n in changed:
        click.echo(f"  changed: {n.note_path}")
    for p in deleted:
        click.echo(f"  deleted: {p}")


def _print_hits(query, mode, hits) -> None:
    if not hits:
        click.echo(f'No results for "{query}" ({mode}).')
        return
    click.echo(click.style(f'"{query}"  ·  {mode}  ·  {len(hits)} results', dim=True))
    width = len(str(len(hits)))
    for i, h in enumerate(hits, 1):
        snippet = " ".join(h["text"].split())[:200]
        click.echo("─" * 60)
        click.echo(f"{str(i).rjust(width)}. {click.style(h['note_path'], bold=True)}")
        click.echo(f"{' ' * (width + 2)}{click.style(h['breadcrumb'], fg='cyan')}")
        click.echo(f"{' ' * (width + 2)}{snippet}")
