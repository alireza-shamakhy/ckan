# -*- coding: utf-8 -*-

import logging
import pathlib
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union
from typing_extensions import TypedDict
import yaml

from .key import Key
from .option import Flag, Option
from .utils import FormatHandler

if TYPE_CHECKING:
    from . import Declaration


log = logging.getLogger(__name__)
option_types = {
    "base": "declare",
    "bool": "declare_bool",
    "int": "declare_int",
}

handler: FormatHandler[Callable[..., None]] = FormatHandler()


class OptionV1(TypedDict, total=False):
    key: str
    default: Any
    default_callable: str
    default_args: Dict[str, Any]
    description: str
    validators: str
    type: str
    disabled: bool
    ignored: bool
    experimental: bool
    internal: bool


class GroupV1(TypedDict):
    annotation: str
    options: List[OptionV1]


class DeclarationDictV1(TypedDict):
    version: int
    groups: List[GroupV1]


DeclarationDict = Union[DeclarationDictV1]
load = handler.handle


@handler.register("plugin")
def load_plugin(declaration: "Declaration", name: str):
    from ckan.plugins import IConfigDeclaration, PluginNotFoundException
    from ckan.plugins.core import _get_service

    try:
        plugin: Any = _get_service(name)
    except PluginNotFoundException:
        log.error("Plugin %s does not exists", name)
        return

    if not IConfigDeclaration.implemented_by(type(plugin)):
        log.error("Plugin %s does not declare config options", name)
        return

    plugin.declare_config_options(declaration, Key())


@handler.register("dict")
def load_dict(declaration: "Declaration", definition: DeclarationDict):
    from ckan.logic.schema import config_declaration_v1
    from ckan.logic import ValidationError
    from ckan.lib.navl.dictization_functions import validate

    version = definition["version"]
    if version == 1:

        data, errors = validate(definition, config_declaration_v1())
        if any(
            options for item in errors["groups"] for options in item["options"]
        ):
            raise ValidationError(errors)
        for group in data["groups"]:
            if group["annotation"]:
                declaration.annotate(group["annotation"])
            for details in group["options"]:
                factory = option_types[details["type"]]
                option: Option = getattr(declaration, factory)(
                    details["key"], details["default"]
                )
                option.append_validators(details["validators"])

                for flag in Flag:
                    if details.get(flag.name):
                        option._set_flag(flag)

                if details["description"]:
                    option.set_description(details["description"])

                if "default_callable" in details:
                    args = details.get("default_args", {})
                    default = details["default_callable"](**args)
                    option.set_default(default)


@handler.register("core")
def load_core(declaration: "Declaration"):
    source = pathlib.Path(__file__).parent / ".." / "config_declaration.yaml"
    with source.open("r") as stream:
        data = yaml.safe_load(stream)
        load_dict(declaration, data)
