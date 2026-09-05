#!/usr/bin/env python3
"""Check residual v2 parser loss against two selectively fetched XML sources."""
import hashlib
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
spec = importlib.util.spec_from_file_location("source_parser", ROOT / "scripts/build_statpearls_corpus.py")
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)

def main():
    results = []
    for article in ("24945", "29656"):
        path = ROOT / f"data/corpus/statpearls/statpearls_NBK430685/article-{article}.nxml"
        root = ET.parse(path).getroot()
        canonical = root.find(".//book-part-meta/title-group/title")
        title = "".join(canonical.itertext())
        first_citation = next(root.iter("article-title"))
        wrong = "".join(first_citation.itertext())
        chunks = parser.parse_article(path)
        row = {"article_id": article, "path": str(path.relative_to(ROOT)),
               "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
               "canonical_title": title, "first_bibliography_article_title": wrong,
               "parsed_title": chunks[0]["title"],
               "parser_uses_bibliographic_title": chunks[0]["title"].startswith(wrong),
               "chunks": len(chunks)}
        if article == "24945":
            candidates = [e for e in root.iter("list") if "The DSM" not in "".join(e.itertext())
                          and "cognitive deficits do not occur only" in "".join(e.itertext())]
            target = candidates[0]
            lines = parser.render_list(target)
            nested_in_p = target.findall("./list-item/p/list/list-item")
            row.update(raw_top_level_members=len(target.findall("list-item")),
                       raw_nested_members_in_p=len(nested_in_p),
                       rendered_top_level_lines=sum(x.startswith("• ") for x in lines),
                       rendered_indented_lines=sum(x.startswith("  ") for x in lines),
                       nested_member_texts=[" ".join("".join(e.itertext()).split()) for e in nested_in_p],
                       flattened_last_member=lines[-1],
                       group_quantifier_still_present="All 3 of the following" in lines[-1])
            assert len(nested_in_p) == 2 and row["rendered_indented_lines"] == 0
        assert row["parser_uses_bibliographic_title"] and title != wrong
        results.append(row)
    (OUT / "source_parse_repro.json").write_text(json.dumps(results, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(results, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
