from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable

from .markers import camel_import_name, ensure_markers, replace_marked, write_text
from .unpack import PackData

LogFn = Callable[[str], None]

M_ORDER_S = "// series-pack:generated:order:start"
M_ORDER_E = "// series-pack:generated:order:end"
M_IMP_S = "// series-pack:generated:imports:start"
M_IMP_E = "// series-pack:generated:imports:end"
M_POR_S = "// series-pack:generated:portraits:start"
M_POR_E = "// series-pack:generated:portraits:end"
M_NAM_S = "// series-pack:generated:names:start"
M_NAM_E = "// series-pack:generated:names:end"
M_RAR_S = "// series-pack:generated:rarities:start"
M_RAR_E = "// series-pack:generated:rarities:end"
M_SID_S = "// series-pack:generated:seriesOf:start"
M_SID_E = "// series-pack:generated:seriesOf:end"

M_BACK_IMP_S = "// series-pack:generated:back-imports:start"
M_BACK_IMP_E = "// series-pack:generated:back-imports:end"
M_BACK_MAP_S = "// series-pack:generated:back-map:start"
M_BACK_MAP_E = "// series-pack:generated:back-map:end"

M_SERIES_S = "// series-pack:generated:series:start"
M_SERIES_E = "// series-pack:generated:series:end"


def apply_frontend(pack: PackData, fe_root: Path, log: LogFn) -> None:
    doc = pack.series
    series = doc["series"]
    cards: list[dict] = doc["cards"]
    sid = series["id"]
    back_id = series["card_back_id"]
    sname = series["name"]

    imports_dir = fe_root / "src" / "imports"
    imports_dir.mkdir(parents=True, exist_ok=True)

    back_rel = series.get("card_back_file") or f"backs/{back_id}.svg"
    shutil.copy2(pack.root / back_rel, imports_dir / f"{back_id}.svg")
    log(f"FE рубашка → src/imports/{back_id}.svg")

    for c in cards:
        cid = c["id"]
        rel = c.get("file") or f"cards/{cid}.webp"
        shutil.copy2(pack.root / rel, imports_dir / f"{cid}.webp")
    log(f"FE webp: {len(cards)} файлов")

    # cardDetails.json
    details_path = fe_root / "src" / "app" / "cardDetails.json"
    details = json.loads(details_path.read_text(encoding="utf-8"))
    stories = details.setdefault("stories", {})
    for cid, text in pack.stories.items():
        stories[cid] = text
    write_text(details_path, json.dumps(details, ensure_ascii=False, indent=2) + "\n")
    log("FE cardDetails.json обновлён")

    _patch_card_catalog(fe_root, sid, cards, log)
    _patch_card_backs(fe_root, back_id, log)
    _patch_series_meta(fe_root, sid, sname, back_id, log)


def _patch_card_catalog(fe_root: Path, sid: str, cards: list[dict], log: LogFn) -> None:
    path = fe_root / "src" / "lib" / "cardCatalog.ts"
    text = path.read_text(encoding="utf-8")

    text = ensure_markers(text, M_IMP_S, M_IMP_E, insert_before="export interface CatalogEntry")
    text = ensure_markers(
        text, M_ORDER_S, M_ORDER_E, insert_before="];\n\nconst PORTRAITS"
    )
    # If above insert_before not found, try alternate
    if M_ORDER_S not in text:
        text = ensure_markers(text, M_ORDER_S, M_ORDER_E, insert_before="];\n\nconst PORTRAITS:")
    text = ensure_markers(text, M_POR_S, M_POR_E, insert_before="};\n\nconst NAMES")
    text = ensure_markers(text, M_NAM_S, M_NAM_E, insert_before="};\n\nconst RARITIES")
    text = ensure_markers(text, M_RAR_S, M_RAR_E, insert_before="};\n\nexport function catalogIndex")
    text = ensure_markers(
        text, M_SID_S, M_SID_E, insert_before="export function catalogIndex"
    )

    # Read existing generated chunks to append (multi-import support)
    def existing_body(start: str, end: str) -> str:
        import re as _re

        m = _re.search(_re.escape(start) + r"(.*?)" + _re.escape(end), text, _re.DOTALL)
        return (m.group(1) if m else "").strip("\n")

    prev_imp = existing_body(M_IMP_S, M_IMP_E)
    prev_ord = existing_body(M_ORDER_S, M_ORDER_E)
    prev_por = existing_body(M_POR_S, M_POR_E)
    prev_nam = existing_body(M_NAM_S, M_NAM_E)
    prev_rar = existing_body(M_RAR_S, M_RAR_E)
    prev_sid = existing_body(M_SID_S, M_SID_E)

    # Drop previous lines for same series ids if re-import attempted (should be blocked)
    def filter_lines(body: str, ids: set[str]) -> list[str]:
        out = []
        for line in body.splitlines():
            if any(i in line for i in ids):
                continue
            out.append(line)
        return out

    ids = {c["id"] for c in cards}
    imp_lines = filter_lines(prev_imp, ids)
    ord_lines = filter_lines(prev_ord, ids)
    por_lines = filter_lines(prev_por, ids)
    nam_lines = filter_lines(prev_nam, ids)
    rar_lines = filter_lines(prev_rar, ids)
    sid_lines = filter_lines(prev_sid, ids)

    for c in cards:
        cid = c["id"]
        var = camel_import_name(cid)
        imp_lines.append(f'import {var} from "@/imports/{cid}.webp";')
        ord_lines.append(f'  "{cid}",')
        por_lines.append(f'  "{cid}": {var},')
        nam_lines.append(f'  "{cid}": {json.dumps(c["name"], ensure_ascii=False)},')
        rar_lines.append(f'  "{cid}": "{c["rarity"]}",')
        sid_lines.append(f'  "{cid}": "{sid}",')

    text = replace_marked(text, M_IMP_S, M_IMP_E, "\n".join(imp_lines))
    text = replace_marked(text, M_ORDER_S, M_ORDER_E, "\n".join(ord_lines))
    text = replace_marked(text, M_POR_S, M_POR_E, "\n".join(por_lines))
    text = replace_marked(text, M_NAM_S, M_NAM_E, "\n".join(nam_lines))
    text = replace_marked(text, M_RAR_S, M_RAR_E, "\n".join(rar_lines))
    text = replace_marked(text, M_SID_S, M_SID_E, "\n".join(sid_lines))

    # Ensure SERIES_OF / seriesId wiring exists outside markers (done in refactor)
    write_text(path, text)
    log("FE cardCatalog.ts обновлён (generated markers)")


def _patch_card_backs(fe_root: Path, back_id: str, log: LogFn) -> None:
    path = fe_root / "src" / "lib" / "cardBacks.ts"
    text = path.read_text(encoding="utf-8")
    text = ensure_markers(
        text, M_BACK_IMP_S, M_BACK_IMP_E, insert_before="const CARD_BACKS"
    )
    text = ensure_markers(
        text, M_BACK_MAP_S, M_BACK_MAP_E, insert_before="};\n\nexport const DEFAULT_CARD_BACK_ID"
    )

    import re as _re

    def body(start: str, end: str) -> str:
        m = _re.search(_re.escape(start) + r"(.*?)" + _re.escape(end), text, _re.DOTALL)
        return (m.group(1) if m else "").strip("\n")

    var = camel_import_name(back_id.replace("card-back-", "cardBack-")).replace(
        "cardBack", "cardBack"
    )
    # stable var: cardBackClassic from card-back-classic
    parts = back_id.split("-")
    var = parts[0] + "".join(p.title() for p in parts[1:]) + "Img"

    prev_imp = [
        ln
        for ln in body(M_BACK_IMP_S, M_BACK_IMP_E).splitlines()
        if back_id not in ln
    ]
    prev_map = [
        ln
        for ln in body(M_BACK_MAP_S, M_BACK_MAP_E).splitlines()
        if back_id not in ln
    ]
    prev_imp.append(f'import {var} from "@/imports/{back_id}.svg";')
    prev_map.append(f'  "{back_id}": {var},')

    text = replace_marked(text, M_BACK_IMP_S, M_BACK_IMP_E, "\n".join(prev_imp))
    text = replace_marked(text, M_BACK_MAP_S, M_BACK_MAP_E, "\n".join(prev_map))
    write_text(path, text)
    log("FE cardBacks.ts обновлён")


def _patch_series_meta(
    fe_root: Path, sid: str, sname: str, back_id: str, log: LogFn
) -> None:
    path = fe_root / "src" / "lib" / "seriesMeta.ts"
    text = path.read_text(encoding="utf-8")
    text = ensure_markers(
        text, M_SERIES_S, M_SERIES_E, insert_before="};\n\nexport function seriesIdFromSlug"
    )
    if M_SERIES_S not in text:
        text = ensure_markers(
            text, M_SERIES_S, M_SERIES_E, insert_before="export function seriesIdFromSlug"
        )

    import re as _re

    m = _re.search(
        _re.escape(M_SERIES_S) + r"(.*?)" + _re.escape(M_SERIES_E), text, _re.DOTALL
    )
    prev = (m.group(1) if m else "").strip("\n")
    lines = [ln for ln in prev.splitlines() if f'"{sid}"' not in ln and f"'{sid}'" not in ln]
    label = f"Серия «{sname}» · Тираж № 001"
    lines.append(
        f'  "{sid}": {{\n'
        f'    id: "{sid}",\n'
        f"    name: {json.dumps(sname, ensure_ascii=False)},\n"
        f'    cardBackId: "{back_id}",\n'
        f"    boosterLabel: {json.dumps(label, ensure_ascii=False)},\n"
        f"  }},"
    )
    text = replace_marked(text, M_SERIES_S, M_SERIES_E, "\n".join(lines))
    write_text(path, text)
    log("FE seriesMeta.ts обновлён")
