"""Shared fixtures for all tests."""

import tempfile
from pathlib import Path
from typing import Generator

import pytest

from mcp_text_editor.models import (
    EditRequest,
    CreateRequest,
    ReadRequest,
    EditResult,
    FileContent,
)


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def test_file(temp_dir: Path) -> Path:
    """Create a test file in the temporary directory."""
    file_path = temp_dir / "test_file.txt"
    file_path.write_text("Original content\nLine 2\nLine 3")
    return file_path


@pytest.fixture
def non_existent_file(temp_dir: Path) -> Path:
    """Return path to a non-existent file."""
    return temp_dir / "non_existent.txt"


@pytest.fixture
def sample_edit_request(test_file: Path) -> EditRequest:
    """Create a sample EditRequest."""
    return EditRequest(
        path=str(test_file),
        content="Modified content",
        line_start=1,
        line_end=1,
    )


@pytest.fixture
def sample_create_request(non_existent_file: Path) -> CreateRequest:
    """Create a sample CreateRequest."""
    return CreateRequest(
        path=str(non_existent_file),
        content="New file content\nWith multiple lines",
    )


@pytest.fixture
def sample_read_request(test_file: Path) -> ReadRequest:
    """Create a sample ReadRequest."""
    return ReadRequest(path=str(test_file))


@pytest.fixture
def mock_file_content() -> FileContent:
    """Create a mock FileContent object."""
    return FileContent(
        path="/path/to/file.txt",
        content="Mock file content\nLine 2\nLine 3",
    )


@pytest.fixture
def mock_edit_result() -> EditResult:
    """Create a mock EditResult object."""
    return EditResult(
        path="/path/to/file.txt",
        old_content="Old content",
        new_content="New content",
        line_count=1,
    )
