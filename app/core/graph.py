from langgraph.graph import StateGraph, END

from app.models.state import PIDState
from app.core.nodes import (
    cloud_coarse_extraction,
    deterministic_chunking,
    local_batch_extraction,
    cloud_validation,
    insert_postgres,
)


def _route_after_validation(state: PIDState) -> str:
    """Boucle vers le LLM local si le LLM cloud a demandé une réextraction,
    sinon poursuit vers la persistance."""
    if state.get("chunks_to_reextract"):
        return "local_batch_extraction"
    return "insert_postgres"


def build_graph():
    g = StateGraph(PIDState)

    g.add_node("cloud_coarse_extraction", cloud_coarse_extraction)
    g.add_node("deterministic_chunking", deterministic_chunking)
    g.add_node("local_batch_extraction", local_batch_extraction)
    g.add_node("cloud_validation", cloud_validation)
    g.add_node("insert_postgres", insert_postgres)
    # Neo4j volontairement absent du graphe pour l'instant (voir
    # app/core/nodes.py::insert_neo4j, déjà écrit mais non branché).
    # À réintroduire plus tard : ajouter le node + g.add_edge("insert_postgres", "insert_neo4j").

    g.set_entry_point("cloud_coarse_extraction")
    g.add_edge("cloud_coarse_extraction", "deterministic_chunking")
    g.add_edge("deterministic_chunking", "local_batch_extraction")
    g.add_edge("local_batch_extraction", "cloud_validation")

    g.add_conditional_edges(
        "cloud_validation",
        _route_after_validation,
        {
            "local_batch_extraction": "local_batch_extraction",
            "insert_postgres": "insert_postgres",
        },
    )

    g.add_edge("insert_postgres", END)

    return g.compile()