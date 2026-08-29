import sys
import json

from dotenv import load_dotenv
load_dotenv()

from app.core.graph import build_graph
from app.core.chunking import make_document_id


def run(pdf_path: str) -> dict:
    graph = build_graph()
    document_id = make_document_id(pdf_path)

    initial_state = {
        "pdf_path": pdf_path,
        "document_id": document_id,
        "validation_attempt": 0,
        "chunks_to_reextract": [],
        "errors": [],
    }

    return graph.invoke(initial_state)


def _summarize(result: dict) -> None:
    data = result.get("validated_data", {})
    print(f"Equipment   : {len(data.get('equipment', []))}")
    print(f"Instruments : {len(data.get('instruments', []))}")
    print(f"Pipelines   : {len(data.get('pipelines', []))}")
    if result.get("needs_review"):
        print(f"À vérifier manuellement (chunks) : {result['needs_review']}")
    if result.get("errors"):
        print(f"Erreurs : {result['errors']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.main <chemin_vers_le_pdf>")
        sys.exit(1)

    final_state = run(sys.argv[1])
    _summarize(final_state)

    with open("result.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "validated_data": {
                    k: [item.model_dump() for item in v]
                    for k, v in final_state.get("validated_data", {}).items()
                },
                "needs_review": final_state.get("needs_review", []),
                "errors": final_state.get("errors", []),
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print("Résultat détaillé écrit dans result.json")