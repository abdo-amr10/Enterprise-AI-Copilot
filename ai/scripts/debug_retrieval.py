"""One-off diagnostic: inspect live ContextRetrievalService intermediate state.

Does not modify ContextRetrievalService. Imports and calls it exactly as
production code does, via the existing dependency wiring, then prints the
internal values requested for debugging. Safe to delete after use.
"""
import json
import sys

sys.path.insert(0, ".")

from src.api.dependencies import get_copilot_pipeline  # reuse existing wiring


def inspect(question: str) -> None:
    pipeline = get_copilot_pipeline()
    # Adjust attribute path below if your DI wiring nests it differently —
    # it must resolve to the ContextRetrievalService instance actually used
    # at runtime by TextToSQLPipeline.
    service = pipeline._text_to_sql_pipeline._context_retrieval_service

    layer = service._semantic_repository.load()
    results = service.retrieve(question)
    seed_from_results = service._seed_tables(results)
    requested = service._tables_explicitly_requested(question, layer)
    seed_tables = requested or seed_from_results
    relationships = service._connecting_relationships(seed_tables, layer.get("relationships", []))

    print("=" * 60)
    print(f"QUESTION: {question}")
    print("=" * 60)
    print(f"\n[1] retrieve() -> {len(results)} results")
    for r in results:
        payload = r.get("payload", {})
        print(f"    type={r.get('type')!r} mapping={payload.get('mapping')!r} "
              f"from_table={payload.get('from_table')!r} to_table={payload.get('to_table')!r}")

    print(f"\n[2] _seed_tables(results) -> {sorted(seed_from_results)}")
    print(f"\n[3] _tables_explicitly_requested() -> {sorted(requested)}")
    print(f"\n[4] final seed_tables (pre-relationship-completion) -> {sorted(seed_tables)}")
    print(f"\n[5] Customer in _seed_tables(results)? -> {'Customer' in seed_from_results}")
    print(f"\n[6] connecting relationships found -> {len(relationships)}")
    for rel in relationships:
        print(f"    {rel.get('from_table')}.{rel.get('from_column')} -> "
              f"{rel.get('to_table')}.{rel.get('to_column')}  (name={rel.get('name')!r})")

    all_relationships = layer.get("relationships", [])
    involved = {"customers", "branches", "accounts"}

    print("\nRelationships touching customers/branches/accounts:")
    for rel in all_relationships:
         if (
            rel.get("from_table") in involved
            or rel.get("to_table") in involved
         ):
            print(
                  f"    {rel.get('from_table')}.{rel.get('from_column')} -> "
                  f"{rel.get('to_table')}.{rel.get('to_column')} "
                  f"(name={rel.get('name')!r})"
            )

    print(
         "customers appears anywhere in layer['relationships']: ",
         any(
            "customers" in (
                  rel.get("from_table", ""),
                  rel.get("to_table", ""),
            )
            for rel in all_relationships
         ),
      )

if __name__ == "__main__":
    inspect("show me all the accounts in Sergio Parker's branch")
    print("\n\n")
    inspect(
        "Using the banking database, identify the customers who have a credit "
        "score above the average credit score of all customers in their "
        "respective city, and who have at least two accounts associated with "
        "branches located in a different city from the customer's city."
    )