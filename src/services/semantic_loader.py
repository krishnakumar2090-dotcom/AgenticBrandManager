from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SEMANTIC_MODEL_FILE = PROJECT_ROOT / "yaml_files" / "semantic_model.yaml"
RESPONSE_RULES_FILE = PROJECT_ROOT / "yaml_files" / "response_rules.yaml"


class SemanticModelError(Exception):
    """Custom exception for semantic model errors."""

    pass


def load_semantic_model() -> dict:
    """
    Load semantic_model.yaml
    """

    if not SEMANTIC_MODEL_FILE.exists():
        raise FileNotFoundError(f"Semantic model not found: " f"{SEMANTIC_MODEL_FILE}")

    with open(SEMANTIC_MODEL_FILE, "r", encoding="utf-8") as file:

        semantic_model = yaml.safe_load(file)

    validate_semantic_model(semantic_model)

    return semantic_model


def validate_semantic_model(model: dict) -> None:
    """
    Basic validation.
    """

    required_sections = [
        "name",
        "tables",
    ]

    for section in required_sections:

        if section not in model:
            raise SemanticModelError(f"Missing section: {section}")

    if not isinstance(model["tables"], list) or not model["tables"]:
        raise SemanticModelError("model.tables must be a non-empty list")

    for table in model["tables"]:

        if "name" not in table:
            raise SemanticModelError("Every table requires a name")

        if "base_table" not in table:
            raise SemanticModelError(f"Table {table['name']} missing base_table")


def get_model_name(semantic_model: dict) -> str:

    return semantic_model["name"]


def get_tables(semantic_model: dict) -> list:

    return semantic_model.get("tables", [])


def get_table_names(semantic_model: dict) -> list:

    return [table["name"] for table in get_tables(semantic_model)]


def get_physical_table_names(semantic_model: dict) -> set:
    """
    Return the lowercase physical (database) table names,
    as used by the underlying PostgreSQL tables.
    """

    return {
        table["base_table"]["table"].strip().lower()
        for table in get_tables(semantic_model)
    }


def get_relationships(semantic_model: dict) -> list:

    return semantic_model.get("relationships", [])


def get_metrics(semantic_model: dict) -> list:

    return semantic_model.get("metrics", [])


def get_verified_queries(semantic_model: dict) -> list:

    return semantic_model.get("verified_queries", [])


def get_custom_instructions(semantic_model: dict) -> dict:

    return semantic_model.get("module_custom_instructions", {})


def load_response_rules() -> dict:
    """
    Load response_rules.yaml, which defines how SQL should
    rank/order results (e.g. "top N ... arrange in desc
    order") and how final answers should be phrased/formatted.
    Returns an empty dict if the file doesn't exist, so this
    is safe to call even before the file is created.
    """

    if not RESPONSE_RULES_FILE.exists():
        return {}

    with open(RESPONSE_RULES_FILE, "r", encoding="utf-8") as file:

        return yaml.safe_load(file) or {}


# if __name__ == "__main__":

#     semantic_model = load_semantic_model()

#     print("\nSemantic Model Loaded Successfully\n")

#     print(f"Model Name : " f"{semantic_model['name']}")

#     print(f"Tables     : " f"{len(get_tables(semantic_model))}")

#     print(f"Metrics    : " f"{len(get_metrics(semantic_model))}")

#     print(f"Relationships : " f"{len(get_relationships(semantic_model))}")
