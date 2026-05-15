from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogResource:
    key: str
    category: str
    default_exposure: str


RESOURCE_CATALOG = [
    CatalogResource("network", "foundation", "private"),
    CatalogResource("security-groups", "security", "private"),
    CatalogResource("iam-user-groups", "security", "private"),
    CatalogResource("ecr", "runtime", "private"),
    CatalogResource("lambda-runtime", "runtime", "private"),
    CatalogResource("ecs-runtime", "runtime", "private"),
    CatalogResource("alb", "edge", "public-alb"),
    CatalogResource("dynamodb", "state", "private"),
    CatalogResource("ssm-secrets", "config", "private"),
    CatalogResource("kms", "security", "private"),
    CatalogResource("observability", "operations", "private"),
    CatalogResource("cicd-hooks", "operations", "private"),
]
