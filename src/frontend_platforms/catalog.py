"""Materialize user overrides over the complete bundled platform XML baseline."""

from copy import deepcopy
from pathlib import Path, PurePosixPath

from lxml import etree

from frontend_platforms import PlatformRegistry, platform_configuration, platform_component
from retrolibx.adapters.esde.merge import parse_xml, xml_text
from retrolibx.core.executor import PlanExecutor
from retrolibx.core.operations import ExportIntent, TextRequest
from retrolibx.core.options import ExportOptions
from retrolibx.core.planner import ConversionPlanner


def bundled_registry() -> PlatformRegistry:
    directory = Path(__file__).with_name("custom_systems-PG")
    return PlatformRegistry.load(config_dir=directory)


def materialize_catalog(definitions: list, destination: Path) -> dict[str, str]:
    registry = bundled_registry()
    documents = platform_configuration(registry.config_dir)
    root = parse_xml(documents["es_systems.xml"].encode("utf-8"), "systemList")
    nodes = {node.findtext("name"): node for node in root.findall("system")}
    by_id = {item.id: item for item in definitions}
    identities: dict[str, str] = {}
    resolving: set[str] = set()

    def install(item):
        if item.id in identities:
            return identities[item.id]
        if item.id in resolving:
            raise ValueError("平台母体存在循环：" + item.name)
        resolving.add(item.id)
        record = registry.resolve(item.id) or registry.resolve(item.directory)
        identity = record["name"] if record else platform_component(item.id)
        parent_id = install(by_id[item.parent]) if item.parent else None
        old = nodes.get(identity)
        if old is None:
            if parent_id is None:
                raise ValueError("新平台需要选择母体以继承启动配置：" + item.name)
            old = deepcopy(nodes[parent_id])
            root.append(old)
        node = deepcopy(old)
        theme = (nodes[parent_id].findtext("theme") if parent_id and item.mode == "inherit"
                 else record["theme"] if record else item.directory)
        for tag, value in {"name": identity, "fullname": item.name,
                           "path": "%ROMPATH%/" + platform_component(item.directory),
                           "theme": theme}.items():
            child = node.find(tag)
            if child is None:
                child = etree.SubElement(node, tag)
            child.text = value
        root.replace(old, node)
        nodes[identity] = node
        identities[item.id] = identity
        resolving.remove(item.id)
        return identity

    for item in definitions:
        install(item)
    documents["es_systems.xml"] = xml_text(root)
    intent = ExportIntent(texts=[TextRequest(destination=PurePosixPath(name), content=text)
                                 for name, text in documents.items()])
    plan = ConversionPlanner().plan(intent, source_root=registry.config_dir, target_root=destination,
                                    source_format="platform-catalog", target_format="platform-config",
                                    options=ExportOptions(conflict="overwrite"))
    PlanExecutor().execute(plan)
    return identities

