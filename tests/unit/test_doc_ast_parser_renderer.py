import json
import pathlib
from jedwal.posts.parsers import ast
from jedwal.posts.parsers import google_docs_parser
from jedwal.posts.parsers import markdown_renderer


def test_construct_simple_ast():
    ast_impl = ast.Root(
        children=[
            ast.Heading(depth=1, children=[ast.Text(value="My big post!")]),
            ast.Paragraph(
                children=[
                    ast.Text(value="Wow some text!"),
                    ast.Text(value="Wow some more text!"),
                ]
            ),
            ast.Code(lang="ts", value="export async const go = () => {return 1}"),
        ]
    )

    # Test round trip serialization
    assert ast.Root.model_validate(ast_impl.model_dump()) == ast_impl


def test_google_doc_to_markdown():
    base_path = pathlib.Path.cwd() / "tests" / "data"
    google_doc_json_path = base_path / "test_google_document.json"
    markdown_path = base_path / "test_markdown_output.md"

    google_doc_json_path = json.loads(google_doc_json_path.read_text())
    parser = google_docs_parser.GoogleDocsParser()
    ast_tree = parser.parse(google_doc_json_path)

    renderer = markdown_renderer.MarkdownRenderer()
    assert renderer.render(ast_tree) == markdown_path.read_text()
