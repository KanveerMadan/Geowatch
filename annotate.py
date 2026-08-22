#!/usr/bin/env python3
"""
GeoWatch Copilot — Annotation Pipeline
======================================
Local tool for generating ground-truth labels from pipeline run outputs.
These labels become training data for SegFormer fine-tuning (Path B).

Usage:
    python annotate.py data/pipeline_runs/dharavi_20260620_230924/result.json

Keyboard shortcuts (shown in UI):
    0-9  — assign one of the 10 land-cover categories
    u    — mark as unknown / unclassifiable
    s    — skip this segment (excluded from training data)
    b    — go back to previous segment
    q    — quit and save

Output:
    annotations.json saved alongside result.json in the same run directory.
    Schema: {run_id, segment_id, bbox, human_label, tile_suggested_label,
             crop_top_category, crop_confidence, annotation_priority,
             annotated_at, skipped}
"""

# ── FROZEN — DO NOT RUN (audit finding C28) ──────────────────────────────────
# Deliberately placed ABOVE the imports so an attempted run refuses before the
# module-level tkinter/PIL import work happens. Guarded on __main__ rather than
# executed unconditionally so that importing this module (e.g. to reuse a
# helper) is unaffected — the freeze is on running an annotation session, not
# on the file existing.
if __name__ == "__main__":
    import sys as _sys

    _sys.stderr.write("""
================================================================================
FROZEN — annotate.py will not run.  (audit finding C28)
================================================================================

C28: annotate.py joins masks.json to result.json by segment_id in order to
embed mask_rle into each annotation record. On post-Phase-2 runs those ids do
not correspond — 30.6% of segments (11/36) measured mis-joined on a fresh run,
with a clean one-position shift from id 25 onward. Root cause is C9:
result.json ids come from a counter over surviving segments while masks.json
ids come from a counter over all masks.

Running an annotation session against such a run would pair one segment's bbox
with another segment's mask and write that into annotations.json, where it
becomes permanent training data. Per C30, the one tool that could catch it
(verify_masks.py) checks only that segment ids EXIST in masks.json, never that
they refer to the same geometry — so nothing downstream would detect the
corruption.

Existing training data is not affected: the eleven training runs predate
Phase 2. The damage would be done by the NEXT annotation round, and baking a
mis-joined mask into annotations.json is irreversible.

THIS FREEZE LIFTS WHEN EITHER:
  * C9 and C30 are both fixed — segment ids join correctly across result.json
    and masks.json, AND verify_masks.py validates id CORRESPONDENCE rather
    than mere existence; or
  * the SAM decision removes segment-based annotation entirely, making the
    segment_id join moot.

Do not bypass this guard to label "just a few". There is no partial-safety
mode: the join is wrong for an unknown subset of every post-Phase-2 run, and
which subset is not visible from inside the annotation UI.
================================================================================
""")
    raise SystemExit(2)


import json
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont
from datetime import datetime
from pathlib import Path
from typing import Optional


# ── Category definitions ──────────────────────────────────────────────────────

CATEGORIES = [
    "dense_informal_roofing",
    "sparse_informal_roofing",
    "unpaved_dirt_road",
    "paved_road",
    "open_drainage_channel",
    "standing_water",
    "vegetation_clearing",
    "active_construction",
    "dense_vegetation",
    "open_waste",
]

# Colors for category highlighting in the tile overview (R, G, B)
CATEGORY_COLORS = {
    "dense_informal_roofing":  (220, 60,  60),
    "sparse_informal_roofing": (240, 140, 80),
    "unpaved_dirt_road":       (180, 140, 80),
    "paved_road":              (120, 120, 180),
    "open_drainage_channel":   (80,  160, 220),
    "standing_water":          (40,  100, 200),
    "vegetation_clearing":     (210, 200, 80),
    "active_construction":     (200, 80,  200),
    "dense_vegetation":        (60,  180, 80),
    "open_waste":              (140, 100, 60),
    "unknown":                 (160, 160, 160),
    "skipped":                 (80,  80,  80),
}

# Keyboard shortcut → category index
KEY_MAP = {str(i): CATEGORIES[i] for i in range(10)}
KEY_MAP["u"] = "unknown"
KEY_MAP["s"] = "__skip__"
KEY_MAP["b"] = "__back__"
KEY_MAP["q"] = "__quit__"


# ── Utilities ─────────────────────────────────────────────────────────────────
def load_masks_rle(run_dir: str) -> dict:
    """
    Load the RLE-encoded masks saved by segmentation.py's save_masks(),
    keyed by segment_id. Returns {} if the file doesn't exist (e.g. an
    older pipeline run from before this fix -- falls back gracefully,
    those segments just won't have mask_rle in their annotation).
    """
    masks_path = os.path.join(run_dir, "masks.json")  # adjust if pipeline.py uses a different name
    if not os.path.exists(masks_path):
        print(f"  Note: no masks.json found at {masks_path} -- "
              f"annotations for this run will only have bbox, not real mask shape.")
        return {}
    with open(masks_path) as f:
        raw = json.load(f)
    return {str(m["segment_id"]): m.get("mask_rle") for m in raw if "mask_rle" in m}
 
 
def load_run(result_json_path: str) -> tuple[dict, str, list]:
    """Load result.json and return (run_data, run_dir, segments)."""
    with open(result_json_path) as f:
        run_data = json.load(f)
    run_dir = str(Path(result_json_path).parent)
    segments = run_data.get("segments", [])
    return run_data, run_dir, segments


def load_annotations(annotations_path: str) -> dict:
    """Load existing annotations or return empty dict keyed by segment_id."""
    if os.path.exists(annotations_path):
        with open(annotations_path) as f:
            data = json.load(f)
        # Re-key by segment_id for fast lookup
        return {str(a["segment_id"]): a for a in data.get("annotations", [])}
    return {}


def save_annotations(annotations_path: str, run_id: str, annotations: dict):
    """
    Save annotations to disk. Called after every label — crash-safe.
    annotations: dict keyed by str(segment_id)
    """
    output = {
        "run_id": run_id,
        "annotation_tool_version": "1.0",
        "last_saved": datetime.utcnow().isoformat() + "Z",
        "total_annotated": sum(
            1 for a in annotations.values() if not a.get("skipped", False)
        ),
        "total_skipped": sum(
            1 for a in annotations.values() if a.get("skipped", False)
        ),
        "annotations": list(annotations.values()),
    }
    with open(annotations_path, "w") as f:
        json.dump(output, f, indent=2)


def sort_segments_by_priority(segments: list) -> list:
    """
    Sort segments for annotation order:
    1. High-priority first (crop disagrees with tile label)
    2. Within each group: largest area first (more informative)
    """
    return sorted(
        segments,
        key=lambda s: (0 if s.get("annotation_priority", False) else 1, -s.get("area", 0))
    )


def build_tile_overview(
    tile_path: str,
    segments: list,
    annotations: dict,
    active_segment_id: Optional[int],
    display_size: int = 400,
) -> Image.Image:
    """
    Render tile overview with all segment bboxes drawn.
    - Gray box = unannotated
    - Colored box = annotated (color by category)
    - Orange thick box = currently active segment
    - Red thick box = high-priority annotation candidate
    """
    base = Image.open(tile_path).convert("RGB")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for seg in segments:
        sid = seg["segment_id"]
        x, y, w, h = seg["bbox"]
        ann = annotations.get(str(sid))

        if sid == active_segment_id:
            color = (255, 165, 0, 220)  # orange — active
            width = 3
        elif ann and ann.get("skipped"):
            color = (*CATEGORY_COLORS["skipped"], 100)
            width = 1
        elif ann:
            label = ann["human_label"]
            rgb = CATEGORY_COLORS.get(label, (160, 160, 160))
            color = (*rgb, 180)
            width = 2
        elif seg.get("annotation_priority", False):
            color = (255, 50, 50, 160)  # red — high priority unannotated
            width = 2
        else:
            color = (200, 200, 200, 100)  # gray — unannotated
            width = 1

        draw.rectangle([x, y, x + w, y + h], outline=color, width=width)

    combined = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

    # Scale to display size maintaining aspect ratio
    combined.thumbnail((display_size, display_size), Image.LANCZOS)
    return combined


def build_crop_image(tile_path: str, bbox: list, display_size: int = 220) -> Image.Image:
    """Crop segment from tile and scale up for display."""
    x, y, w, h = bbox
    tile = Image.open(tile_path).convert("RGB")
    crop = tile.crop((x, y, x + w, y + h))

    # Scale up small crops so they're actually visible
    scale = max(1, display_size // max(w, h, 1))
    new_w = min(w * scale, display_size)
    new_h = min(h * scale, display_size)
    crop = crop.resize((new_w, new_h), Image.NEAREST)
    return crop


# ── Main annotation UI ────────────────────────────────────────────────────────

class AnnotationApp:
    def __init__(self, root: tk.Tk, result_json_path: str):
        self.root = root
        self.result_json_path = result_json_path

        # Load data
        self.run_data, self.run_dir, raw_segments = load_run(result_json_path)
        self.run_id = self.run_data.get("run_id", "unknown")
        self.tile_path = self.run_data.get("primary_tile", "")

        if not os.path.exists(self.tile_path):
            # Try path relative to run_dir
            tile_basename = os.path.basename(self.tile_path)
            alt_path = os.path.join(self.run_dir, "tiles", tile_basename)
            if os.path.exists(alt_path):
                self.tile_path = alt_path
            else:
                messagebox.showerror("Error", f"Tile not found:\n{self.tile_path}")
                root.destroy()
                return

        self.segments = sort_segments_by_priority(raw_segments)
        self.masks_rle = load_masks_rle(self.run_dir)
        self.annotations_path = os.path.join(self.run_dir, "annotations.json")
        self.annotations = load_annotations(self.annotations_path)

        self.current_idx = 0
        self._find_first_unannotated()

        # Build UI
        root.title(f"GeoWatch Annotation — {self.run_id}")
        root.configure(bg="#1a1a2e")
        root.resizable(True, True)
        self._build_ui()
        self._render_current()

        # Bind keyboard
        root.bind("<Key>", self._on_key)
        root.focus_set()

    def _find_first_unannotated(self):
        """Jump to first unannotated segment (respects priority ordering)."""
        for i, seg in enumerate(self.segments):
            sid = str(seg["segment_id"])
            if sid not in self.annotations:
                self.current_idx = i
                return
        # All annotated — stay at end
        self.current_idx = len(self.segments) - 1

    def _build_ui(self):
        root = self.root

        # ── Top bar ──
        top_bar = tk.Frame(root, bg="#0f0f23", pady=6)
        top_bar.pack(fill="x")

        self.title_label = tk.Label(
            top_bar, text="", font=("JetBrains Mono", 11, "bold"),
            fg="#7ec8e3", bg="#0f0f23"
        )
        self.title_label.pack(side="left", padx=12)

        self.progress_label = tk.Label(
            top_bar, text="", font=("JetBrains Mono", 10),
            fg="#aaaaaa", bg="#0f0f23"
        )
        self.progress_label.pack(side="right", padx=12)

        # ── Progress bar ──
        prog_frame = tk.Frame(root, bg="#1a1a2e", pady=4)
        prog_frame.pack(fill="x", padx=12)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            prog_frame, variable=self.progress_var, maximum=100, length=400
        )
        self.progress_bar.pack(fill="x")

        # ── Main content area ──
        content = tk.Frame(root, bg="#1a1a2e")
        content.pack(fill="both", expand=True, padx=12, pady=8)

        # Left: tile overview
        left_panel = tk.Frame(content, bg="#1a1a2e")
        left_panel.pack(side="left", fill="both", expand=False, padx=(0, 12))

        tk.Label(
            left_panel, text="TILE OVERVIEW", font=("JetBrains Mono", 9),
            fg="#555577", bg="#1a1a2e"
        ).pack(anchor="w")

        self.tile_canvas = tk.Label(left_panel, bg="#0f0f23", relief="flat")
        self.tile_canvas.pack()

        # Legend below tile
        legend_frame = tk.Frame(left_panel, bg="#1a1a2e", pady=4)
        legend_frame.pack(fill="x")
        self._build_legend(legend_frame)

        # Right: segment detail + controls
        right_panel = tk.Frame(content, bg="#1a1a2e")
        right_panel.pack(side="left", fill="both", expand=True)

        # Crop image
        tk.Label(
            right_panel, text="SEGMENT CROP", font=("JetBrains Mono", 9),
            fg="#555577", bg="#1a1a2e"
        ).pack(anchor="w")

        self.crop_canvas = tk.Label(right_panel, bg="#0f0f23", relief="flat")
        self.crop_canvas.pack(pady=(0, 8))

        # Segment info
        info_frame = tk.Frame(right_panel, bg="#1a1a2e")
        info_frame.pack(fill="x")

        self.seg_info_label = tk.Label(
            info_frame, text="", font=("JetBrains Mono", 9),
            fg="#cccccc", bg="#1a1a2e", justify="left", anchor="w"
        )
        self.seg_info_label.pack(fill="x")

        # Score bars
        self.scores_frame = tk.Frame(right_panel, bg="#1a1a2e")
        self.scores_frame.pack(fill="x", pady=(8, 0))

        tk.Label(
            self.scores_frame, text="TILE SCORES  (raw cosine)",
            font=("JetBrains Mono", 8), fg="#555577", bg="#1a1a2e"
        ).pack(anchor="w")

        self.score_bars_frame = tk.Frame(self.scores_frame, bg="#1a1a2e")
        self.score_bars_frame.pack(fill="x")

        # Category buttons + keyboard hints
        btn_frame = tk.Frame(right_panel, bg="#1a1a2e", pady=8)
        btn_frame.pack(fill="x")

        tk.Label(
            btn_frame, text="ASSIGN LABEL  (keyboard shortcut in [ ])",
            font=("JetBrains Mono", 8), fg="#555577", bg="#1a1a2e"
        ).pack(anchor="w")

        self.cat_buttons_frame = tk.Frame(btn_frame, bg="#1a1a2e")
        self.cat_buttons_frame.pack(fill="x", pady=4)
        self._build_category_buttons()

        # Nav buttons
        nav_frame = tk.Frame(right_panel, bg="#1a1a2e", pady=4)
        nav_frame.pack(fill="x")

        for text, cmd, fg in [
            ("[b] Back",          self._go_back,       "#aaaaaa"),
            ("[s] Skip",          self._skip,           "#ff9944"),
            ("[u] Unknown",       self._label_unknown,  "#888888"),
            ("[q] Save & Quit",   self._quit,           "#44cc88"),
        ]:
            tk.Button(
                nav_frame, text=text, command=cmd,
                font=("JetBrains Mono", 9), fg=fg, bg="#252540",
                activebackground="#333360", relief="flat", padx=8, pady=4,
                cursor="hand2"
            ).pack(side="left", padx=(0, 6))

        # Status bar
        self.status_label = tk.Label(
            root, text="", font=("JetBrains Mono", 9),
            fg="#888888", bg="#0f0f23", anchor="w", pady=4
        )
        self.status_label.pack(fill="x", padx=12)

    def _build_legend(self, parent):
        """Small color legend for the tile overview."""
        items = [
            ("Active",          (255, 165, 0)),
            ("High priority",   (255, 50,  50)),
            ("Unannotated",     (200, 200, 200)),
            ("Skipped",         (80,  80,  80)),
        ]
        for label, color in items:
            row = tk.Frame(parent, bg="#1a1a2e")
            row.pack(anchor="w")
            color_hex = "#{:02x}{:02x}{:02x}".format(*color)
            tk.Label(
                row, text="■", fg=color_hex, bg="#1a1a2e",
                font=("JetBrains Mono", 8)
            ).pack(side="left")
            tk.Label(
                row, text=f" {label}", fg="#888888", bg="#1a1a2e",
                font=("JetBrains Mono", 8)
            ).pack(side="left")

    def _build_category_buttons(self):
        """Build 0-9 category buttons in a grid."""
        frame = self.cat_buttons_frame
        for widget in frame.winfo_children():
            widget.destroy()

        for i, cat in enumerate(CATEGORIES):
            rgb = CATEGORY_COLORS[cat]
            hex_color = "#{:02x}{:02x}{:02x}".format(*rgb)
            short = cat.replace("_", " ")
            btn = tk.Button(
                frame,
                text=f"[{i}] {short}",
                command=lambda c=cat: self._label_segment(c),
                font=("JetBrains Mono", 8),
                fg=hex_color, bg="#1e1e36",
                activebackground="#2a2a50",
                relief="flat", padx=6, pady=3,
                cursor="hand2", anchor="w"
            )
            row, col = divmod(i, 2)
            btn.grid(row=row, column=col, sticky="ew", padx=2, pady=2)

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

    def _render_current(self):
        """Render tile overview, crop, and info for current segment."""
        if not self.segments:
            self._set_status("No segments to annotate.")
            return

        seg = self.segments[self.current_idx]
        sid = seg["segment_id"]
        ann = self.annotations.get(str(sid))

        # Title + progress
        n_done = len(self.annotations)
        n_total = len(self.segments)
        priority_label = "  ⚑ HIGH PRIORITY" if seg.get("annotation_priority") else ""
        self.title_label.config(
            text=f"Segment {self.current_idx + 1}/{n_total}  |  ID: {sid}{priority_label}"
        )
        self.progress_label.config(
            text=f"{n_done}/{n_total} labeled"
        )
        pct = (n_done / n_total * 100) if n_total else 0
        self.progress_var.set(pct)

        # Tile overview
        overview = build_tile_overview(
            self.tile_path, self.segments, self.annotations, active_segment_id=sid
        )
        overview_tk = ImageTk.PhotoImage(overview)
        self.tile_canvas.config(image=overview_tk)
        self.tile_canvas._image = overview_tk  # prevent GC

        # Crop
        try:
            crop = build_crop_image(self.tile_path, seg["bbox"])
            crop_tk = ImageTk.PhotoImage(crop)
            self.crop_canvas.config(image=crop_tk)
            self.crop_canvas._image = crop_tk
        except Exception as e:
            self.crop_canvas.config(text=f"Crop error:\n{e}", image="")

        # Segment info
        bbox = seg["bbox"]
        existing_label = ann["human_label"] if ann else "—"
        priority_str = "YES — crop disagrees with tile" if seg.get("annotation_priority") else "no"
        info_lines = [
            f"Bbox: x={bbox[0]} y={bbox[1]} w={bbox[2]} h={bbox[3]}",
            f"Area: {seg.get('area', '?')} px",
            f"Tile suggested: {seg.get('category', '?')}  ({seg.get('confidence', '?'):.4f})",
            f"Crop top: {seg.get('crop_top_category', '?')}  ({seg.get('crop_confidence', '?'):.4f})",
            f"Annotation priority: {priority_str}",
            f"Current label: {existing_label}",
        ]
        self.seg_info_label.config(text="\n".join(info_lines))

        # Score bars
        self._render_score_bars(seg)

        # Status
        status = f"Run: {self.run_id}  |  Tile: {os.path.basename(self.tile_path)}"
        if ann:
            skipped = ann.get("skipped", False)
            status += f"  |  Already labeled: {'[SKIPPED]' if skipped else ann['human_label']}"
        self._set_status(status)

    def _render_score_bars(self, seg: dict):
        """Render horizontal score bars for all_scores (raw cosine)."""
        frame = self.score_bars_frame
        for widget in frame.winfo_children():
            widget.destroy()

        scores = seg.get("all_scores", {})
        if not scores:
            return

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        min_score = min(scores.values())
        max_score = max(scores.values())
        score_range = max(max_score - min_score, 0.001)

        tile_cat = seg.get("category", "")
        crop_cat = seg.get("crop_top_category", "")

        for cat, score in sorted_scores:
            row = tk.Frame(frame, bg="#1a1a2e")
            row.pack(fill="x", pady=1)

            # Label
            label_text = cat.replace("_", " ")
            rgb = CATEGORY_COLORS.get(cat, (160, 160, 160))
            hex_color = "#{:02x}{:02x}{:02x}".format(*rgb)

            markers = ""
            if cat == tile_cat:
                markers += " ◀T"
            if cat == crop_cat:
                markers += " ◀C"

            tk.Label(
                row, text=f"{label_text}{markers}",
                width=28, anchor="w",
                font=("JetBrains Mono", 7), fg=hex_color, bg="#1a1a2e"
            ).pack(side="left")

            # Bar
            bar_frame = tk.Frame(row, bg="#0f0f23", height=10, width=180)
            bar_frame.pack(side="left", padx=2)
            bar_frame.pack_propagate(False)

            fill_pct = (score - min_score) / score_range
            fill_w = max(int(fill_pct * 178), 2)
            tk.Frame(bar_frame, bg=hex_color, height=10, width=fill_w).place(x=0, y=0)

            # Score value
            tk.Label(
                row, text=f"{score:.4f}",
                font=("JetBrains Mono", 7), fg="#888888", bg="#1a1a2e"
            ).pack(side="left", padx=2)

    def _label_segment(self, category: str):
        seg = self.segments[self.current_idx]
        sid = seg["segment_id"]
 
        self.annotations[str(sid)] = {
            "segment_id": sid,
            "bbox": seg["bbox"],
            "mask_rle": self.masks_rle.get(str(sid)),   # <-- ADDED
            "area": seg.get("area"),
            "human_label": category,
            "tile_suggested_label": seg.get("category"),
            "tile_confidence": seg.get("confidence"),
            "crop_top_category": seg.get("crop_top_category"),
            "crop_confidence": seg.get("crop_confidence"),
            "annotation_priority": seg.get("annotation_priority", False),
            "annotated_at": datetime.utcnow().isoformat() + "Z",
            "skipped": False,
        }
 
        save_annotations(self.annotations_path, self.run_id, self.annotations)
        self._set_status(f"Labeled segment {sid} as '{category}'. Saved.")
        self._advance()


    def _label_unknown(self):
        self._label_segment("unknown")

    def _skip(self):
        """Skip segment — excluded from training data."""
        seg = self.segments[self.current_idx]
        sid = seg["segment_id"]

        self.annotations[str(sid)] = {
            "segment_id": sid,
            "bbox": seg["bbox"],
            "area": seg.get("area"),
            "human_label": None,
            "tile_suggested_label": seg.get("category"),
            "tile_confidence": seg.get("confidence"),
            "crop_top_category": seg.get("crop_top_category"),
            "crop_confidence": seg.get("crop_confidence"),
            "annotation_priority": seg.get("annotation_priority", False),
            "annotated_at": datetime.utcnow().isoformat() + "Z",
            "skipped": True,
        }

        save_annotations(self.annotations_path, self.run_id, self.annotations)
        self._set_status(f"Segment {sid} skipped.")
        self._advance()

    def _advance(self):
        """Move to next segment. Skip already-annotated ones on first pass."""
        # Try to find next unannotated
        for i in range(self.current_idx + 1, len(self.segments)):
            sid = str(self.segments[i]["segment_id"])
            if sid not in self.annotations:
                self.current_idx = i
                self._render_current()
                return

        # All done or reviewing — just go to next
        if self.current_idx < len(self.segments) - 1:
            self.current_idx += 1
        self._render_current()
        self._check_completion()

    def _go_back(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            self._render_current()

    def _check_completion(self):
        n_done = sum(1 for a in self.annotations.values() if not a.get("skipped", False))
        n_total = len(self.segments)
        if n_done >= n_total:
            messagebox.showinfo(
                "All segments labeled!",
                f"All {n_total} segments have been labeled.\n"
                f"Annotations saved to:\n{self.annotations_path}"
            )

    def _quit(self):
        save_annotations(self.annotations_path, self.run_id, self.annotations)
        n_done = sum(1 for a in self.annotations.values() if not a.get("skipped", False))
        n_skip = sum(1 for a in self.annotations.values() if a.get("skipped", False))
        messagebox.showinfo(
            "Saved",
            f"Annotations saved.\n\n"
            f"Labeled: {n_done}\n"
            f"Skipped: {n_skip}\n"
            f"Remaining: {len(self.segments) - len(self.annotations)}\n\n"
            f"File: {self.annotations_path}"
        )
        self.root.destroy()

    def _on_key(self, event: tk.Event):
        key = event.char.lower()
        if key in KEY_MAP:
            action = KEY_MAP[key]
            if action == "__skip__":
                self._skip()
            elif action == "__back__":
                self._go_back()
            elif action == "__quit__":
                self._quit()
            else:
                self._label_segment(action)

    def _set_status(self, msg: str):
        self.status_label.config(text=msg)



# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python annotate.py <path/to/result.json>")
        print()
        print("Example:")
        print("  python annotate.py data/pipeline_runs/dharavi_20260620_230924/result.json")
        sys.exit(1)

    result_json_path = sys.argv[1]

    if not os.path.exists(result_json_path):
        print(f"Error: File not found: {result_json_path}")
        sys.exit(1)

    root = tk.Tk()

    # Style ttk progress bar
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        "Horizontal.TProgressbar",
        troughcolor="#0f0f23",
        background="#7ec8e3",
        lightcolor="#7ec8e3",
        darkcolor="#7ec8e3",
    )

    app = AnnotationApp(root, result_json_path)
    root.mainloop()


if __name__ == "__main__":
    main()