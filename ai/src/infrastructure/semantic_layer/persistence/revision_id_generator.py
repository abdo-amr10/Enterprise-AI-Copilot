from uuid import uuid4


class RevisionIdGenerator:
    """Generates unique Semantic Layer revision IDs."""

    @staticmethod
    def generate() -> str:
        return f"rev-{uuid4().hex}"