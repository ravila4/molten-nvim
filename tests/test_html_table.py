import pytest
from molten.html_table import html_tables_to_markdown

PANDAS_HTML = """<div>
<style scoped>
    .dataframe tbody tr th:only-of-type { vertical-align: middle; }
    .dataframe thead th { text-align: right; }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>job_id</th>
      <th>n</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>abc</td>
      <td>1</td>
    </tr>
    <tr>
      <th>1</th>
      <td>de</td>
      <td>22</td>
    </tr>
  </tbody>
</table>
</div>"""


@pytest.mark.parametrize("html", ["", "<div>hello</div>", "<table></table>"])
def test_returns_none_when_no_table(html: str) -> None:
    assert html_tables_to_markdown(html) is None


def test_pandas_dataframe_with_index_column() -> None:
    assert html_tables_to_markdown(PANDAS_HTML) == "\n".join(
        [
            "|     | job_id | n   |",
            "| --- | ------ | --- |",
            "| 0   | abc    | 1   |",
            "| 1   | de     | 22  |",
        ]
    )


def test_first_row_is_header_without_thead() -> None:
    html = "<table><tr><td>a</td><td>b</td></tr><tr><td>1</td><td>2</td></tr></table>"
    assert html_tables_to_markdown(html) == "\n".join(
        ["| a   | b   |", "| --- | --- |", "| 1   | 2   |"]
    )


def test_pipe_in_cell_is_escaped() -> None:
    html = "<table><tr><th>h</th></tr><tr><td>a|b</td></tr></table>"
    assert html_tables_to_markdown(html) == "\n".join(["| h    |", "| ---- |", "| a\\|b |"])


def test_html_entities_are_decoded() -> None:
    html = (
        '<table><tr><th class="blank">&nbsp;</th><th>v</th></tr>'
        "<tr><td>x</td><td>&lt;tag&gt; &amp; y</td></tr></table>"
    )
    assert html_tables_to_markdown(html) == "\n".join(
        ["|     | v         |", "| --- | --------- |", "| x   | <tag> & y |"]
    )


@pytest.mark.parametrize("br", ["<br>", "<br/>", "<br />"])
def test_br_becomes_space(br: str) -> None:
    html = f"<table><tr><th>h</th></tr><tr><td>line1{br}line2</td></tr></table>"
    assert html_tables_to_markdown(html) == "\n".join(
        ["| h           |", "| ----------- |", "| line1 line2 |"]
    )


def test_nested_inline_tags_are_flattened() -> None:
    html = '<table><tr><th>h</th></tr><tr><td><b>bold</b> <a href="x">link</a></td></tr></table>'
    assert html_tables_to_markdown(html) == "\n".join(
        ["| h         |", "| --------- |", "| bold link |"]
    )


def test_whitespace_is_collapsed() -> None:
    html = "<table><tr><th>h</th></tr><tr><td>\n   a \n  b\n</td></tr></table>"
    assert html_tables_to_markdown(html) == "\n".join(["| h   |", "| --- |", "| a b |"])


def test_multiindex_two_thead_rows() -> None:
    html = (
        "<table><thead>"
        "<tr><th></th><th>x</th><th>y</th></tr>"
        "<tr><th>idx</th><th></th><th></th></tr>"
        "</thead><tbody>"
        "<tr><th>0</th><td>1</td><td>2</td></tr>"
        "</tbody></table>"
    )
    assert html_tables_to_markdown(html) == "\n".join(
        [
            "|     | x   | y   |",
            "| --- | --- | --- |",
            "| idx |     |     |",
            "| 0   | 1   | 2   |",
        ]
    )


def test_nan_and_empty_cells() -> None:
    html = "<table><tr><th>a</th><th>b</th></tr><tr><td>NaN</td><td></td></tr></table>"
    assert html_tables_to_markdown(html) == "\n".join(
        ["| a   | b   |", "| --- | --- |", "| NaN |     |"]
    )


def test_ragged_rows_are_padded() -> None:
    html = "<table><tr><th>a</th><th>b</th></tr><tr><td>1</td></tr></table>"
    assert html_tables_to_markdown(html) == "\n".join(
        ["| a   | b   |", "| --- | --- |", "| 1   |     |"]
    )


def test_multiple_tables_joined_by_blank_line() -> None:
    html = (
        "<table><tr><th>a</th></tr><tr><td>1</td></tr></table>"
        "<p>between</p>"
        "<table><tr><th>b</th></tr><tr><td>2</td></tr></table>"
    )
    assert html_tables_to_markdown(html) == "\n".join(
        ["| a   |", "| --- |", "| 1   |", "", "| b   |", "| --- |", "| 2   |"]
    )


def test_no_trailing_newline() -> None:
    result = html_tables_to_markdown(PANDAS_HTML)
    assert result is not None
    assert not result.endswith("\n")
