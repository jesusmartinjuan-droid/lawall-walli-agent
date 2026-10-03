"""The exact file extensions OpenAI's `code_interpreter` tool can read
(per OpenAI's documentation — https://developers.openai.com/api/docs/guides/tools-code-interpreter,
re-verify if OpenAI changes this). Accepting a file outside this list would
let staff upload something the model can never actually use, so both the
local-upload path and the Drive-sync path reject anything not in here with
a clear error instead of silently storing a useless file."""

import os

SUPPORTED_FILE_EXTENSIONS = frozenset(
    {
        # Documents
        ".doc",
        ".docx",
        ".pdf",
        ".pptx",
        # Data
        ".csv",
        ".json",
        ".xml",
        ".xlsx",
        # Code
        ".c",
        ".cs",
        ".cpp",
        ".java",
        ".py",
        ".php",
        ".rb",
        ".js",
        ".ts",
        ".sh",
        ".tex",
        # Images
        ".jpeg",
        ".jpg",
        ".gif",
        ".png",
        # Other
        ".html",
        ".md",
        ".txt",
        ".css",
        ".pkl",
        ".tar",
        ".zip",
    }
)


def is_supported_file_type(filename: str) -> bool:
    extension = os.path.splitext(filename)[1].lower()
    return extension in SUPPORTED_FILE_EXTENSIONS
