from __future__ import annotations

import sys
import click
from cisco_config_generator.__about__ import __version__
from cisco_config_generator.logging_setup import setup_logging


@click.command()
@click.option(
    "--pack", "-p",
    default="default",
    show_default=True,
    help="Pack name (folder under packs/) or full path to a pack directory.",
)
@click.option(
    "--workbook", "-w",
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the intent workbook (.xlsx).",
)
@click.option(
    "--output", "-o",
    default="output",
    show_default=True,
    help="Directory to write generated config files.",
)
@click.option(
    "--no-tui",
    is_flag=True,
    default=False,
    help="Run headless without the interactive TUI.",
)
@click.option(
    "--version",
    is_flag=True,
    default=False,
    is_eager=True,
    help="Print version and exit.",
)
def main(
    pack: str,
    workbook: str | None,
    output: str,
    no_tui: bool,
    version: bool,
) -> None:
    """Cisco Config Generator — generate per-device IOS-XE access switch configuration files."""
    if version:
        click.echo(f"Cisco Config Generator v{__version__}")
        sys.exit(0)

    if no_tui:
        if not workbook:
            click.echo("Error: --workbook is required when running with --no-tui.", err=True)
            sys.exit(1)
        _run_headless(pack, workbook, output)
    else:
        _run_tui(pack, workbook, output)


def _run_headless(pack: str, workbook: str, output: str) -> None:
    from cisco_config_generator.pack_loader import resolve_pack_path
    from cisco_config_generator.settings_loader import load_pack_settings
    from cisco_config_generator.orchestrator import Orchestrator
    from cisco_config_generator.workbook.validators import ValidationError

    pack_path = resolve_pack_path(pack)
    settings = load_pack_settings(pack_path)
    log = setup_logging(settings.get("log_level", "INFO"))

    try:
        orchestrator = Orchestrator(pack_path=pack_path, workbook_path=workbook, output_dir=output)
        results = orchestrator.run()
        for path in results:
            log.info(f"[green]Written:[/green] {path}")
        log.info(f"[bold green]Done! {len(results)} file(s) generated.[/bold green]")
    except ValidationError as e:
        log.error("Validation failed:")
        for err in e.errors:
            log.error(f"  \u2022 {err}")
        sys.exit(1)
    except Exception as e:
        log.error(f"Error: {e}")
        sys.exit(1)


def _run_tui(pack: str, workbook: str | None, output: str) -> None:
    from cisco_config_generator.tui.app import CiscoConfigGeneratorApp

    app = CiscoConfigGeneratorApp(
        initial_pack=pack,
        initial_workbook=workbook or "",
        initial_output=output,
    )
    app.run()
