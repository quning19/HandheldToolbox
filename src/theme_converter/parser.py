"""ES-DE resource graph with guarded values and include-local path resolution.

This reads themes; it does not render them. Loading order follows ThemeData.cpp.
Conditional values carry regions, so unrelated language/color/ratio choices do
not require enumerating their full Cartesian product.
"""
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import re
from copy import deepcopy
from lxml import etree

from retrolibx.adapters.esde.merge import parse_xml
from retrolibx.errors import ValidationError
from frontend_common.jobs import checkpoint

PARSER_VERSION = "esde-graph-2"
POLICY_VERSION = "resource-policy-3"
DIMENSIONS = ("colorScheme", "fontSize", "language", "variant", "aspectRatio")
TOKEN = re.compile(r"\$\{([^{}]+)\}")
PATH_PROPERTIES = {
    "path", "default", "staticImage", "staticVideo", "defaultImage", "defaultVideo",
    "defaultFolderImage", "fontPath", "backgroundImage", "selectorImage", "selectorImagePath",
    "customButtonIcon", "customBadgeIcon", "customControllerIcon", "customIcon",
    "scrollSound", "navigationSound", "selectSound", "launchSound",
}
COPY_ONLY = re.compile(r"overlay|mask|shadow|gradient|vignette|selector|button|font|spacer|logo|(?:^|[/ _-])icons?(?:[/ _-]|$)", re.I)
ART = re.compile(r"art|background|controller|console|hardware|screenshot|capsule|wallpaper|cover|fanart|physicalmedia|system[-_]image", re.I)


@dataclass
class Value:
    text: str
    template: str
    region: dict = field(default_factory=dict)


@dataclass
class Resource:
    source: Path
    destination: PurePosixPath
    role: str
    origin: str
    branch: dict
    inherited: bool = True


@dataclass
class Analysis:
    resources: dict = field(default_factory=dict)
    documents: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    edges: list = field(default_factory=list)


def names(text):
    return {item for item in re.split(r"[\s,]+", text or "") if item}


def intersect(left, right):
    result = dict(left)
    for key, values in right.items():
        result[key] = result[key] & values if key in result else values
        if not result[key]:
            return None
    return result


def subtract(region, covered, domains):
    """Disjoint boxes for region minus covered; used for ordered overrides."""
    if intersect(region, covered) is None:
        return [region]
    remainder, inside = [], dict(region)
    for key, values in covered.items():
        current = inside.get(key, domains[key])
        outside = current - values
        if outside:
            remainder.append({**inside, key: outside})
        inside[key] = current & values
    return remainder


class ThemeParser:
    def __init__(self, source: Path, cancelled=lambda: False):
        self.source = source.resolve()
        self.cancelled = cancelled
        self.files = {}
        self.xml = {}
        self.domains = {key: frozenset({"__default__"}) for key in DIMENSIONS}
        # One exact-case index also makes behavior on Windows match Android.
        for path in self.source.rglob("*"):
            checkpoint(cancelled)
            if path.is_symlink() or path.is_junction():
                raise ValidationError("主题中不允许链接：" + str(path))
            if path.is_file() and ".git" not in path.relative_to(self.source).parts:
                self.files[path.relative_to(self.source).as_posix()] = path
        capabilities = self.read_xml(PurePosixPath("capabilities.xml"), "themeCapabilities")
        for key in DIMENSIONS:
            declared = set()
            for node in capabilities.findall(key):
                declared |= names(node.get("name") or node.text)
            # Language branches have a declared <language> list in modern ES-DE.
            self.domains[key] = frozenset(declared or {"__default__"})
        # Read only referenced XML. Themes may ship unused templates, examples,
        # or draft fragments which ES-DE never loads. Branch domains come from
        # capabilities, rather than from an audit of every XML in the directory.

    def read_xml(self, relative, expected="theme"):
        key = str(relative)
        if key not in self.xml:
            raw = self.files[key].read_bytes()
            try:
                self.xml[key] = parse_xml(raw, expected)
            except ValidationError as original:
                if expected != "theme":
                    raise ValidationError(f"{relative}: {original}") from original
                # pugixml permits multiple document elements; ES-DE loads the
                # first direct <theme>. Keep configuration XML strictly parsed.
                content = re.sub(br"^\s*<\?xml\s[^?]*\?>", b"", raw.removeprefix(b"\xef\xbb\xbf"), count=1)
                try:
                    wrapper = parse_xml(b"<themeDocument>" + content + b"</themeDocument>", "themeDocument")
                    theme = wrapper.find("theme")
                    if theme is None:
                        raise original
                    self.xml[key] = theme
                except ValidationError as exc:
                    raise ValidationError(f"{relative}: {exc}") from exc
        return self.xml[key]

    def relative(self, document, path):
        if not path or path.startswith((":", "~", "/", "\\")) or re.match(r"^[A-Za-z]:", path):
            raise ValidationError("主题资源不是可随主题迁移的相对路径：" + path)
        # Normalize '..' only after checking the resolved destination stays inside.
        result = (self.source / str(document.parent) / path).resolve()
        if not result.is_relative_to(self.source):
            raise ValidationError("主题资源越界：" + path)
        return PurePosixPath(result.relative_to(self.source).as_posix())

    def analyze(self, source_system, target_system, label, source_name="", target_name="", source_fullname=""):
        self.result = Analysis()
        self.environment = {}
        self.target_values = {
            "system.theme": target_system, "system.name": target_name or target_system,
            "system.fullName": label,
            "system.theme.noCollections": target_system, "system.name.noCollections": target_name or target_system,
            "system.fullName.noCollections": label,
        }
        source_values = {**self.target_values, "system.theme": source_system,
                         "system.name": source_name or source_system,
                         "system.fullName": source_fullname or source_name or source_system,
                         "system.theme.noCollections": source_system,
                         "system.name.noCollections": source_name or source_system,
                         "system.fullName.noCollections": source_fullname or source_name or source_system}
        for key, text in source_values.items():
            self.environment[key] = [Value(text, "${" + key + "}")]
        target = PurePosixPath(target_system) / "theme.xml"
        mother = PurePosixPath(source_system) / "theme.xml"
        entry = target if str(target) in self.files else mother if str(mother) in self.files else PurePosixPath("theme.xml")
        output = target if entry == mother else entry
        if str(entry) not in self.files:
            raise ValidationError("主题缺少根目录或平台目录 theme.xml")
        self.load(entry, output, {}, [], label)
        return self.result

    def render_target(self, template):
        return TOKEN.sub(lambda match: self.target_values.get(match[1], match[0]), template)

    def resolve(self, raw, region):
        values = [Value("", "", region)]
        offset = 0
        for token in TOKEN.finditer(raw):
            literal = raw[offset:token.start()]
            options = self.environment.get(token[1], [Value(token[0], token[0])])
            following = []
            for value in values:
                for option in options:
                    mask = intersect(value.region, option.region)
                    if mask is not None:
                        following.append(Value(value.text + literal + option.text, value.template + literal + option.template, mask))
            values = following
            offset = token.end()
            if len(values) > 4096:
                raise ValidationError("主题单条路径分支过多，需要扩充解析策略：" + raw)
        tail = raw[offset:]
        return [Value(value.text + tail, value.template + tail, value.region) for value in values]

    def assign(self, name, raw, region):
        additions = [value for value in self.resolve(raw, region) if value.text]
        old = self.environment.get(name, [])
        for addition in additions:
            kept = []
            for value in old:
                kept.extend(Value(value.text, value.template, mask)
                            for mask in subtract(value.region, addition.region, self.domains))
            old = kept + [addition]
        self.environment[name] = old

    def load(self, relative, destination, region, stack, label):
        checkpoint(self.cancelled)
        if str(relative) in stack:
            raise ValidationError("主题 include 循环：" + " → ".join(stack + [str(relative)]))
        if len(stack) >= 64:
            raise ValidationError("主题 include 嵌套过深")
        root = self.read_xml(relative)
        if relative != destination:
            self.copy_document(relative, destination, root, label)
        self.parse_node(root, relative, destination, region, stack + [str(relative)], label)

    def copy_document(self, relative, destination, root, label):
        if str(destination) in self.files:
            return
        clone = deepcopy(root)
        changed = False
        for node in clone.iter("systemName"):
            node.text = label
            changed = True
        # Preserve the complete XML structure, comments and localized metadata.
        self.result.documents[str(destination)] = etree.tostring(clone, encoding="unicode")
        self.result.edges.append({"type": "xml", "source": str(relative), "target": str(destination), "renamed": changed})

    def branch(self, node, key, relative, destination, region, stack, label):
        selected = frozenset(names(node.get("name")))
        if key == "variant" and "all" in selected:
            selected = self.domains[key]
        if not selected:
            self.result.errors.append(f"{relative}: <{key}> 缺少 name")
            return
        mask = intersect(region, {key: selected})
        if mask is not None:
            self.parse_node(node, relative, destination, mask, stack, label)

    def parse_node(self, root, relative, destination, region, stack, label):
        # ES-DE deliberately does not use XML document order across tag classes.
        for block in root.findall("variables"):
            for variable in block:
                if isinstance(variable.tag, str):
                    self.assign(variable.tag, (variable.text or "").strip(), region)
        simple_branch = root.tag in {"colorScheme", "fontSize", "language"}
        for key in (() if simple_branch else ("colorScheme", "fontSize", "language")):
            for node in root.findall(key):
                self.branch(node, key, relative, destination, region, stack, label)
        for include in root.findall("include"):
            raw = (include.text or "").strip()
            for value in self.resolve(raw, region):
                target_text = self.render_target(value.template)
                if TOKEN.search(value.text) or TOKEN.search(target_text):
                    self.result.errors.append(f"{relative}: 无法解析 include {raw}")
                    continue
                origin = self.relative(relative, value.text)
                target = self.relative(destination, target_text)
                actual = target if str(target) in self.files else origin
                if str(actual) not in self.files:
                    if "${" in raw:
                        # ES-DE permits absent variable includes, but platform metadata can inherit _default.
                        fallback = origin.with_name("_default.xml")
                        if target != origin and str(fallback) in self.files:
                            actual = fallback
                        else:
                            self.result.warnings.append(f"可选 include 不存在：{origin}")
                            continue
                    else:
                        self.result.errors.append(f"必需 include 不存在：{origin}")
                        continue
                self.load(actual, target, value.region, stack, label)
        if simple_branch:
            return  # ES-DE loads only variables/includes from these branch types.
        for view in root.findall("view"):
            for component in view:
                if not isinstance(component.tag, str):
                    continue
                for prop in component:
                    if not isinstance(prop.tag, str):
                        continue
                    if prop.tag in PATH_PROPERTIES:
                        self.resource(prop, component, relative, destination, region)
                    elif prop.tag not in {"imageType", "metadata", "gameSelector", "text"}:
                        # Unknown path-valued properties must be visible in the report.
                        if "${system." in (prop.text or "") and re.search(r"\.(png|webp|jpg|svg|mp4|gif)\b", prop.text or "", re.I):
                            self.result.errors.append(f"{relative}: 未支持的资源属性 {component.tag}.{prop.tag}")
        for key in ("variant", "aspectRatio"):
            if key == root.tag:
                continue
            for node in root.findall(key):
                self.branch(node, key, relative, destination, region, stack, label)
        if root.find("feature") is not None or root.find("formatVersion") is not None:
            self.result.errors.append(f"{relative}: 旧版主题 feature/formatVersion 不受 ES-DE 当前格式支持")

    def resource(self, prop, component, relative, destination, region):
        raw = (prop.text or "").strip()
        if not raw:
            return
        for value in self.resolve(raw, region):
            target_text = self.render_target(value.template)
            if value.text.startswith(":"):
                continue  # ES-DE built-in resource, copied by neither tool nor theme.
            if TOKEN.search(value.text) or TOKEN.search(target_text):
                self.result.errors.append(f"{relative}: 无法解析资源 {raw}")
                continue
            origin = self.relative(relative, value.text)
            target = self.relative(destination, target_text)
            if origin == target:
                continue  # shared/static resource is already included in the complete theme.
            if str(target) in self.files:
                self.result.edges.append({"type": "existing", "target": str(target)})
                continue
            if str(origin) not in self.files:
                fallback = component.find("default")
                if fallback is None:
                    fallback = component.find("defaultImage")
                text_fallback = component.tag in {"carousel", "grid"} and prop.tag == "staticImage"
                component_name = component.get("name", "")
                base_name = re.sub(r"[_-]custom$", "", component_name, flags=re.I)
                layered_fallback = component.tag == "image" and base_name != component_name and any(
                    sibling.tag == "image" and sibling.get("name") == base_name and any(
                        sibling.find(key) is not None for key in ("path", "default", "imageType")
                    ) for sibling in component.getparent()
                )
                # If the original also has no decorative layer, preserve that
                # empty layer instead of inventing required art for the target.
                empty_decoration = component.tag == "image" and re.search(
                    r"overlay|mask|shadow|gradient|vignette", component_name + " " + str(origin), re.I
                ) is not None
                if fallback is not None or prop.tag in {"default", "defaultImage", "defaultVideo"} or text_fallback or layered_fallback or empty_decoration:
                    mechanism = "原版空装饰层" if empty_decoration else "下层素材" if layered_fallback else "列表文字" if text_fallback and fallback is None else "主题默认"
                    self.result.warnings.append(f"沿用{mechanism}回退：{target}")
                    self.result.edges.append({"type": "fallback", "target": str(target), "mechanism": mechanism})
                else:
                    self.result.errors.append(f"平台素材及母体素材均缺失：{target} ← {origin}")
                continue
            context = " ".join((component.tag, component.get("name", ""), str(origin)))
            # Specific illustration roles win over a generic folder name such
            # as carousel-icons-art/capsule/controller. Plain icons remain copies.
            semantic_context = component.get("name", "") + " " + str(origin)
            decorative = re.search(r"overlay|mask|shadow|gradient|vignette|selector|button|font|spacer|logo", semantic_context, re.I)
            role = "copy" if decorative else "art" if ART.search(semantic_context) else "copy" if COPY_ONLY.search(context) else "unknown"
            if role == "unknown" and origin.suffix.lower() in {".png", ".webp", ".jpg", ".jpeg"}:
                self.result.errors.append(f"素材用途不明确，已保留原样，需确认规则：{origin}")
            resource = Resource(self.files[str(origin)], target, role, str(relative),
                                {key: sorted(items) for key, items in value.region.items()})
            previous = self.result.resources.get(str(target))
            if previous and previous.source != resource.source:
                self.result.errors.append(f"不同分支将不同资源写入同一路径：{target}")
            else:
                self.result.resources[str(target)] = resource
            self.result.edges.append({"type": "resource", "source": str(origin), "target": str(target),
                                      "role": role, "property": component.tag + "." + prop.tag, "branch": resource.branch})
