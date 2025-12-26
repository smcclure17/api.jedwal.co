import json
import pathlib

from jedwal.posts.parsers import ast, google_docs_parser, markdown_renderer


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

    google_doc_json = json.loads(google_doc_json_path.read_text())
    parser = google_docs_parser.GoogleDocsParser()
    ast_tree = parser.parse(google_doc_json)

    renderer = markdown_renderer.MarkdownRenderer()
    assert renderer.render(ast_tree) == markdown_path.read_text()


def test_jsx_in_source_doc():
    ast_impl = ast.Root(
        children=[
            ast.Paragraph(
                children=[
                    ast.Text(
                        value='<Image src="/bgmp.png" alt="BGMP Logo" width={1200} height={630} />'
                    ),
                ]
            )
        ]
    )

    renderer = markdown_renderer.MarkdownRenderer()
    output = '<Image src="/bgmp.png" alt="BGMP Logo" width={1200} height={630} />'
    assert renderer.render(ast_impl) == output


def test_jsx_in_google_doc():
    # fmt: off
    source_doc = {
        "body": {
            "content": [
                {
                    "startIndex": 230,
                    "endIndex": 298,
                    "paragraph": {
                        "elements": [
                            {
                                "startIndex": 230,
                                "endIndex": 298,
                                "textRun": {
                                    "content": "<Image src=\"/bgmp.png\" alt=\"BGMP Logo\" width={1200} height={630} />\n",
                                    "textStyle": {}
                                }
                            }
                        ],
                        "paragraphStyle": {
                            "namedStyleType": "NORMAL_TEXT",
                            "direction": "LEFT_TO_RIGHT",
                        },
                    },
                }
            ]
        }
    }
    # fmt: on

    parser = google_docs_parser.GoogleDocsParser()
    ast_tree = parser.parse(source_doc)

    expected = ast.Root(
        children=[
            ast.Paragraph(
                type="paragraph",
                children=[
                    ast.Text(
                        type="text",
                        value='<Image src="/bgmp.png" alt="BGMP Logo" width={1200} height={630} />',
                    )
                ],
            )
        ]
    )
    ast_tree == expected
