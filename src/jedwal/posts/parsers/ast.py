from abc import ABC
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Node(BaseModel, ABC):
    """
    Base abstract interface representing any node in the tree.
    All nodes must have a 'type' field.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    type: str


class LiteralNode(Node, ABC):
    """
    Abstract interface for nodes that contain a literal value.
    Extends Node and adds a 'value' field.
    """

    value: str


class Parent(Node, ABC):
    """
    Abstract interface for nodes that contain other nodes as children.
    Children are limited to MdastContent types.
    """

    children: list["Content"]


class Frontmatter(Node):
    type: Literal["frontmatter"] = "frontmatter"
    value: str
    data: dict | None = None

    @classmethod
    def from_text(cls, value: str):
        """Parse YAML frontmatter and create Frontmatter node with data dict"""
        data = yaml.safe_load(value)
        return cls(value=value, data=data)


class Root(Parent):
    """Root of the document.

    We might add e.g. metadata or Frontmatter fields later.
    """

    type: Literal["root"] = "root"
    frontmatter: Frontmatter | None = None


class Text(LiteralNode):
    type: Literal["text"] = "text"


class Paragraph(Parent):
    """
    Represents a paragraph of phrasing content.
    """

    type: Literal["paragraph"] = "paragraph"
    children: list["Content"]


class Heading(Parent):
    """
    Represents a heading with a specific depth level.
    """

    type: Literal["heading"] = "heading"
    depth: int = Field(..., ge=1, le=6)  # 1-6 for h1-h6
    children: list["Content"]


class Code(LiteralNode):
    """
    Represents a block of preformatted text. Note that
    code blocks should keep spacing as-is
    """

    type: Literal["code"] = "code"
    lang: str | None = None


class Break(Node):
    """Line break"""

    type: Literal["break"] = "break"


class Link(Parent):
    type: Literal["link"] = "link"
    url: str
    children: list["Content"]


class Emphasis(Parent):
    type: Literal["emphasis"] = "emphasis"
    children: list["Content"]


class Strong(Parent):
    type: Literal["strong"] = "strong"
    children: list["Content"]


class Image(Node):
    type: Literal["image"] = "image"
    url: str
    title: str | None = None
    alt: str | None = None


class Table(Parent):
    type: Literal["table"] = "table"
    align: list[str | None] | None = None
    children: list["Content"]


class TableRow(Parent):
    type: Literal["table_row"] = "table_row"
    children: list["TableCell"]


class TableCell(Parent):
    type: Literal["table_cell"] = "table_cell"
    children: list["Content"]


class ListItem(Parent):
    type: Literal["listItem"] = "listItem"
    spread: bool | None = None
    children: list["Content"]
    indent_level: int = 0


class List(Parent):
    type: Literal["list"] = "list"
    ordered: bool = False
    start: int | None = None
    spread: bool | None = None
    children: list[ListItem]


# TODO: narrow content types for certain children for
# better validation
Content = (
    Text
    | Strong
    | Emphasis
    | Link
    | Image
    | Break
    | Paragraph
    | Heading
    | Code
    | Table
    | TableRow
    | TableCell
    | List
    | ListItem
)

InlineNode = Image | Link | Strong | Emphasis
