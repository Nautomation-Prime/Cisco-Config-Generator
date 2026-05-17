from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Log,
    Select,
    Static,
)
from textual.reactive import reactive

from cisco_config_generator.pack_loader import list_available_packs, resolve_pack_path
from cisco_config_generator.settings_loader import load_pack_settings
from cisco_config_generator.logging_setup import get_logger


class CiscoConfigGeneratorApp(App):
    """Textual TUI for the Cisco Config Generator."""

    CSS = """
    Screen {
        background: $surface;
    }
    #config-panel {
        width: 40;
        padding: 1 2;
        border: round $primary;
    }
    #log-panel {
        padding: 1 2;
        border: round $primary-lighten-2;
    }
    .field-label {
        margin-top: 1;
        color: $text-muted;
    }
    #run-btn {
        margin-top: 2;
        width: 100%;
    }
    #status {
        margin-top: 1;
        color: $success;
    }
    """

    TITLE = "Cisco Config Generator"
    SUB_TITLE = "Nautomation Prime"

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+r", "run", "Run"),
    ]

    running: reactive[bool] = reactive(False)

    def __init__(
        self,
        initial_pack: str = "default",
        initial_workbook: str = "",
        initial_output: str = "output",
    ):
        super().__init__()
        self._initial_pack = initial_pack
        self._initial_workbook = initial_workbook
        self._initial_output = initial_output

    def compose(self) -> ComposeResult:
        yield Header()
        packs = list_available_packs() or ["default"]
        pack_options = [(p, p) for p in packs]

        with Horizontal():
            with Vertical(id="config-panel"):
                yield Static("[bold]Configuration[/bold]")
                yield Label("Pack:", classes="field-label")
                yield Select(
                    options=pack_options,
                    value=self._initial_pack if self._initial_pack in packs else packs[0],
                    id="pack-select",
                )
                yield Label("Workbook Path:", classes="field-label")
                yield Input(
                    placeholder="Path to intent.xlsx",
                    value=self._initial_workbook,
                    id="workbook-input",
                )
                yield Label("Output Directory:", classes="field-label")
                yield Input(
                    placeholder="output",
                    value=self._initial_output,
                    id="output-input",
                )
                yield Button("Run [Ctrl+R]", variant="success", id="run-btn")
                yield Static("", id="status")

            with Vertical(id="log-panel"):
                yield Static("[bold]Output[/bold]")
                yield Log(id="log-view", auto_scroll=True)

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            self.action_run()

    def action_run(self) -> None:
        if self.running:
            return
        workbook = self.query_one("#workbook-input", Input).value.strip()
        output = self.query_one("#output-input", Input).value.strip() or "output"
        pack_select = self.query_one("#pack-select", Select)
        pack = str(pack_select.value) if pack_select.value else "default"

        if not workbook:
            self._set_status("[red]Please specify a workbook path.[/red]")
            return
        if not Path(workbook).exists():
            self._set_status(f"[red]Workbook not found: {workbook}[/red]")
            return

        self.running = True
        self._set_status("[yellow]Running...[/yellow]")
        self._clear_log()

        thread = threading.Thread(
            target=self._run_orchestrator,
            args=(pack, workbook, output),
            daemon=True,
        )
        thread.start()

    def _run_orchestrator(self, pack: str, workbook: str, output: str) -> None:
        from cisco_config_generator.orchestrator import Orchestrator
        from cisco_config_generator.workbook.validators import ValidationError

        try:
            pack_path = resolve_pack_path(pack)

            def progress(msg: str) -> None:
                self.call_from_thread(self._append_log, msg)

            orchestrator = Orchestrator(
                pack_path=pack_path,
                workbook_path=workbook,
                output_dir=output,
                on_progress=progress,
            )
            results = orchestrator.run()
            for path in results:
                self.call_from_thread(self._append_log, f"[green]Written:[/green] {path}")
            self.call_from_thread(
                self._set_status,
                f"[bold green]Done! {len(results)} file(s) generated.[/bold green]"
            )
        except ValidationError as e:
            msgs = ["[red]Validation errors:[/red]"] + [f"  \u2022 {err}" for err in e.errors]
            for m in msgs:
                self.call_from_thread(self._append_log, m)
            self.call_from_thread(self._set_status, "[red]Validation failed.[/red]")
        except Exception as e:
            self.call_from_thread(self._append_log, f"[red]Error:[/red] {e}")
            self.call_from_thread(self._set_status, "[red]Error — see log.[/red]")
        finally:
            self.call_from_thread(setattr, self, "running", False)

    def _append_log(self, message: str) -> None:
        log_view = self.query_one("#log-view", Log)
        log_view.write_line(message)

    def _clear_log(self) -> None:
        log_view = self.query_one("#log-view", Log)
        log_view.clear()

    def _set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)
