from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from codemaster import portal
from codemaster.config import load as load_config
from codemaster.config import save as save_config
from codemaster.fsutil import Scope
from codemaster.report import FileSheet, Grade, Mark
from codemaster.scrubber import Edits, WashResult

_CHECKED = "\u2611"
_UNCHECKED = "\u2610"

_KIND_INFO: dict[str, str] = {
    "c2pa": "Manifiesto de procedencia C2PA que declara autor/tool de generacion.",
    "exif": "Metadatos EXIF que pueden listar el modelo o la herramienta de generacion.",
    "xmp": "Metadatos XMP (Adobe) que pueden nombrar la aplicacion que creo el archivo.",
    "pdfkey": "Clave de metadatos PDF que puede revelar el productor o generador.",
    "comment": "Comentario en codigo que atribuye la autoria a una herramienta IA.",
    "docstring": "Docstring que describe el codigo como generado por una IA.",
    "glyph": "Glifo Unicode invisible (caracter de control o stealth) inyectado en el texto.",
    "model": "Nombre de modelo de IA (Claude, GPT, Gemini, Llama...) presente en el contenido.",
    "authorship": "Atribucion explicita: 'generado/escrito por' una herramienta IA.",
    "narration": "Frase tipica de narracion asistida ('note that', 'feel free to'...).",
    "fragment": "Marcador de fragmento/placeholder comun en salidas de IA.",
    "handler": "Error interno del analizador al procesar el archivo.",
    "access": "El archivo no pudo leerse.",
}

_GRADE_COLORS = {
    Grade.HUSH: "#888888",
    Grade.SIGNAL: "#b58900",
    Grade.DANGER: "#cc241d",
}

_GRADE_LABEL = {
    Grade.HUSH: "info",
    Grade.SIGNAL: "senal",
    Grade.DANGER: "peligro",
}


def _rank_for(marks: list[Mark]) -> Grade:
    return max((mark.rank for mark in marks), default=Grade.HUSH)


def _verdict(marks: list[Mark], score: float) -> str:
    rank = _rank_for(marks)
    if rank == Grade.DANGER:
        return (
            "Alta probabilidad de procedencia IA: hay senales firmes "
            "(metadatos C2PA/EXIF o atribuciones explicitas a una herramienta)."
        )
    if rank == Grade.SIGNAL:
        return (
            "Posibles senales de IA: patrones de texto, nombres de modelo o "
            "estructura tipica. Conviene revisar antes de publicar."
        )
    return "Sin senales de IA detectadas en este archivo."


@dataclass(frozen=True)
class Row:
    path: Path
    kind: str
    score: float
    marks: list[Mark]


def collect_rows(roots: list[Path], scope: Scope) -> list[Row]:
    rows: list[Row] = []
    for root in roots:
        for sheet in portal.tour([root], scope).sheets:
            blob = portal.blob_of(sheet.path, scope)
            kind = blob.kind if blob is not None else "?"
            rows.append(Row(sheet.path, kind, sheet.score(), list(sheet.marks)))
    return rows


def wash_many(
    paths: list[Path],
    edits: Edits,
    scope: Scope,
    backup: bool,
    report: queue.Queue[tuple[str, WashResult]],
) -> None:
    for path in paths:
        report.put((str(path), portal.wash_path(path, edits, scope, backup, True)))


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("CodeMaster - Saneamiento de huellas AI")
        root.geometry("980x760")

        self.scope = Scope()
        self.rows: list[Row] = []
        self.selected: set[int] = set()

        self.path_var = tk.StringVar()
        self.comments = tk.BooleanVar(value=True)
        self.docstrings = tk.BooleanVar(value=True)
        self.meta = tk.BooleanVar(value=True)
        self.glyphs = tk.BooleanVar(value=True)
        self.backup = tk.BooleanVar(value=True)
        self.strong_only = tk.BooleanVar(value=False)
        self._load_prefs()

        self._build()
        self._set_busy(False)

    # ------------------------------------------------------------------ UI

    def _build(self) -> None:
        top = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        top.pack(fill=tk.X)

        ttk.Label(top, text="Ruta:").pack(side=tk.LEFT)
        entry = ttk.Entry(top, textvariable=self.path_var, width=64)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(top, text="Archivo...", command=self._pick_file).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(top, text="Carpeta...", command=self._pick_folder).pack(
            side=tk.LEFT, padx=2
        )

        actions = ttk.Frame(self.root, padding=(8, 4))
        actions.pack(fill=tk.X)
        self.analyze_btn = ttk.Button(
            actions, text="Analizar", command=self._analyze_async
        )
        self.analyze_btn.pack(side=tk.LEFT)

        opts = ttk.LabelFrame(self.root, text="Limpiar", padding=(8, 4))
        opts.pack(fill=tk.X, padx=8, pady=4)
        ttk.Checkbutton(opts, text="comentarios", variable=self.comments).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Checkbutton(opts, text="docstrings", variable=self.docstrings).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Checkbutton(opts, text="metadatos", variable=self.meta).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Checkbutton(opts, text="glifos invisibles", variable=self.glyphs).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Checkbutton(opts, text="respaldo .bak", variable=self.backup).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Checkbutton(
            opts, text="solo evidencia fuerte", variable=self.strong_only
        ).pack(side=tk.LEFT, padx=6)

        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        table_frame = ttk.Frame(main_pane)
        main_pane.add(table_frame, weight=3)

        columns = ("sel", "path", "kind", "score", "marks", "worst", "kinds")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", selectmode="browse"
        )
        self.tree.heading("sel", text="")
        self.tree.heading("path", text="Archivo")
        self.tree.heading("kind", text="Tipo")
        self.tree.heading("score", text="Score")
        self.tree.heading("marks", text="Marcas")
        self.tree.heading("worst", text="Peor")
        self.tree.heading("kinds", text="Senales")
        self.tree.column("sel", width=32, stretch=False, anchor=tk.CENTER)
        self.tree.column("path", width=320)
        self.tree.column("kind", width=60, stretch=False)
        self.tree.column("score", width=60, stretch=False, anchor=tk.CENTER)
        self.tree.column("marks", width=60, stretch=False, anchor=tk.CENTER)
        self.tree.column("worst", width=70, stretch=False, anchor=tk.CENTER)
        self.tree.column("kinds", width=160)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scroll.set)

        detail_frame = ttk.LabelFrame(
            main_pane, text="Detalle de senales", padding=(6, 4)
        )
        main_pane.add(detail_frame, weight=2)

        self.detail = tk.Text(detail_frame, width=46, wrap=tk.WORD, state=tk.DISABLED)
        self.detail.pack(fill=tk.BOTH, expand=True)
        for grade in Grade:
            self.detail.tag_configure(
                _GRADE_LABEL[grade], foreground=_GRADE_COLORS[grade]
            )
        self.detail.tag_configure("head", font=("TkDefaultFont", 10, "bold"))

        bottom = ttk.Frame(self.root, padding=(8, 4))
        bottom.pack(fill=tk.X)
        self.summary_var = tk.StringVar(value="Sin analizar")
        ttk.Label(bottom, textvariable=self.summary_var).pack(side=tk.LEFT)
        ttk.Button(bottom, text="Todo", command=self._select_all).pack(
            side=tk.RIGHT, padx=2
        )
        ttk.Button(bottom, text="Nada", command=self._select_none).pack(
            side=tk.RIGHT, padx=2
        )
        self.clean_btn = ttk.Button(
            bottom, text="Limpiar seleccion...", command=self._clean_async
        )
        self.clean_btn.pack(side=tk.RIGHT, padx=8)

        log_frame = ttk.LabelFrame(self.root, text="Registro", padding=(8, 4))
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.log = tk.Text(log_frame, height=6, state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.analyze_btn.configure(state=state)
        self.clean_btn.configure(state=state)
        self.root.configure(cursor="watch" if busy else "")

    def _load_prefs(self) -> None:
        cfg = load_config()
        self.strong_only.set(bool(cfg.strong_only))
        if cfg.last_path:
            self.path_var.set(cfg.last_path)

    def _save_prefs(self) -> None:
        cfg = load_config()
        cfg.strong_only = self.strong_only.get()
        cfg.last_path = self.path_var.get().strip()
        save_config(cfg)

    # -------------------------------------------------------------- actions

    def _pick_file(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Elegir archivo",
            filetypes=[("Todos los archivos", "*.*")],
        )
        if chosen:
            self.path_var.set(chosen)

    def _pick_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Elegir carpeta / proyecto")
        if chosen:
            self.path_var.set(chosen)

    def _analyze_async(self) -> None:
        raw = self.path_var.get().strip()
        if not raw:
            messagebox.showwarning("Falta la ruta", "Elegi un archivo o carpeta.")
            return
        root = Path(raw)
        if not root.exists():
            messagebox.showerror("Ruta invalida", f"No existe: {root}")
            return
        self._set_busy(True)
        self._log(f"Analizando: {root}")
        threading.Thread(target=self._analyze_worker, args=(root,), daemon=True).start()

    def _analyze_worker(self, root: Path) -> None:
        try:
            rows = collect_rows([root], self.scope)
        except Exception as exc:  # pragma: no cover - defensive
            error = exc
            self.root.after(0, lambda: self._log(f"Error al analizar: {error}"))
            self.root.after(0, lambda: self._set_busy(False))
            return
        self.root.after(0, lambda: self._render(rows))

    def _render(self, rows: list[Row]) -> None:
        self.rows = rows
        if self.strong_only.get():
            self.selected = {
                i
                for i, row in enumerate(rows)
                if FileSheet(row.path, row.marks).evidence() in ("strong", "moderate")
            }
        else:
            self.selected = set(range(len(rows)))
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(rows):
            worst = _rank_for(row.marks).name.lower()
            kinds = ", ".join(sorted({mark.kind for mark in row.marks}))
            self.tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(
                    _CHECKED,
                    str(row.path),
                    row.kind,
                    f"{row.score:.2f}",
                    len(row.marks),
                    worst,
                    kinds,
                ),
            )
        self._update_summary()
        self._set_busy(False)
        self._log(f"{len(rows)} archivo(s) analizados.")
        if rows:
            self._show_detail(0)

    def _on_click(self, event: tk.Event) -> None:
        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not item or column != "#1":
            return
        index = int(item)
        if index in self.selected:
            self.selected.discard(index)
        else:
            self.selected.add(index)
        self.tree.set(item, "sel", _CHECKED if index in self.selected else _UNCHECKED)
        self._update_summary()

    def _on_select(self, _event: tk.Event) -> None:
        item = self.tree.focus()
        if item:
            self._show_detail(int(item))

    def _show_detail(self, index: int) -> None:
        if not 0 <= index < len(self.rows):
            return
        row = self.rows[index]
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        self.detail.insert(tk.END, f"{row.path}\n", ("head",))
        self.detail.insert(
            tk.END,
            f"tipo: {row.kind}   score: {row.score:.2f}   "
            f"evidencia: {FileSheet(row.path, row.marks).evidence()}\n\n",
        )
        if not row.marks:
            self.detail.insert(
                tk.END, "Sin senales detectadas.\n", (_GRADE_LABEL[Grade.HUSH],)
            )
        for mark in row.marks:
            tag = _GRADE_LABEL[mark.rank]
            group = f" [{mark.group}]" if mark.group else ""
            self.detail.insert(
                tk.END,
                f"[{_GRADE_LABEL[mark.rank].upper()}]{group} {mark.line}:{mark.col}  "
                f"{mark.kind}: {mark.note}\n",
                (tag,),
            )
        self.detail.insert(
            tk.END, "\n" + _verdict(row.marks, row.score) + "\n", ("head",)
        )
        counts: dict[str, int] = {}
        for mark in row.marks:
            counts[mark.kind] = counts.get(mark.kind, 0) + 1
        groups: dict[str, int] = {}
        for mark in row.marks:
            group = mark.group or "other"
            groups[group] = groups.get(group, 0) + 1
        if groups:
            summary = "  ".join(f"{g}={c}" for g, c in sorted(groups.items()))
            self.detail.insert(tk.END, f"\nGrupos: {summary}\n")
        for kind, count in sorted(counts.items()):
            info = _KIND_INFO.get(kind, "Senal identificada por el analizador.")
            self.detail.insert(tk.END, f"\n{kind} ({count}): {info}\n")
        self.detail.configure(state=tk.DISABLED)

    def _select_all(self) -> None:
        self.selected = set(range(len(self.rows)))
        for index in self.selected:
            self.tree.set(str(index), "sel", _CHECKED)
        self._update_summary()

    def _select_none(self) -> None:
        self.selected.clear()
        for item in self.tree.get_children():
            self.tree.set(item, "sel", _UNCHECKED)
        self._update_summary()

    def _update_summary(self) -> None:
        marks = sum(len(row.marks) for row in self.rows)
        self.summary_var.set(
            f"{len(self.rows)} archivos, {marks} senales, "
            f"{len(self.selected)} seleccionados"
        )

    def _clean_async(self) -> None:
        if not self.rows:
            messagebox.showinfo("Nada que limpiar", "Ejecuta primero Analizar.")
            return
        targets = [self.rows[i].path for i in sorted(self.selected)]
        if not targets:
            messagebox.showinfo("Sin seleccion", "Marca al menos un archivo.")
            return
        edits = Edits(
            comments=self.comments.get(),
            docstrings=self.docstrings.get(),
            glyphs=self.glyphs.get(),
            meta=self.meta.get(),
        )
        wanted = [
            name
            for name, on in (
                ("comentarios", edits.comments),
                ("docstrings", edits.docstrings),
                ("glifos", edits.glyphs),
                ("metadatos", edits.meta),
            )
            if on
        ]
        if not wanted:
            messagebox.showwarning("Nada marcado", "Elegi al menos una categoria.")
            return
        count = len(targets)
        ok = messagebox.askyesno(
            "Confirmar limpieza",
            f"Se limpiaran {count} archivo(s) ({', '.join(wanted)}).\n"
            f"Con respaldo .bak: {self.backup.get()}.\n\n"
            "Los archivos originales se respaldan antes de escribir. Continuar?",
        )
        if not ok:
            return
        self._set_busy(True)
        self._log(f"Limpiando {count} archivo(s)...")
        report: queue.Queue[tuple[str, WashResult]] = queue.Queue()
        threading.Thread(
            target=wash_many,
            args=(targets, edits, self.scope, self.backup.get(), report),
            daemon=True,
        ).start()
        self._poll_clean(report, count)

    def _poll_clean(
        self, report: queue.Queue[tuple[str, WashResult]], pending: int
    ) -> None:
        done = 0
        for _ in range(pending):
            try:
                path, result = report.get_nowait()
            except queue.Empty:
                break
            done += 1
            if result.written:
                self._log(f"limpiado: {path} [{', '.join(result.labels)}]")
            elif result.altered:
                self._log(f"pendiente (sin escribir): {path}")
            else:
                self._log(f"sin cambios: {path}")
        if done < pending:
            self.root.after(100, lambda: self._poll_clean(report, pending))
            return
        self._set_busy(False)
        self._log("Limpieza completada.")
        self._save_prefs()

    def _log(self, line: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, line + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)


def main() -> int:
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0
