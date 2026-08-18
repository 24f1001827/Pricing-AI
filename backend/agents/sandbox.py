from e2b_code_interpreter import Sandbox
from core.config import E2B_API_KEY
from core.logger import get_logger
from typing import Optional
import base64
import json

logger = get_logger(__name__)

def read_output_file_bytes(sandbox: Sandbox, path: str) -> bytes:
    """Read sandbox output as base64 text so binary files are not corrupted."""
    escaped_path = json.dumps(path)
    read_result = sandbox.run_code(f"""
import base64
from pathlib import Path

print(base64.b64encode(Path({escaped_path}).read_bytes()).decode("ascii"))
""")
    if read_result.error:
        raise RuntimeError(read_result.error)

    encoded = "".join(read_result.logs.stdout).strip()
    return base64.b64decode(encoded)

def execute_code(
    code: str,
    files: Optional[dict] = None,
    output_files: Optional[list] = None
) -> dict:
    try:
        logger.info("Executing code in sandbox")
        sandbox = Sandbox.create(api_key=E2B_API_KEY)
        
        try:
            if files:
                for sandbox_path, local_path in files.items():
                    with open(local_path, "rb") as f:
                        sandbox.files.write(sandbox_path, f)
                    logger.info(f"Uploaded {local_path} to sandbox at {sandbox_path}")

            result = sandbox.run_code(code)
            logger.info("Code execution completed")

            output_file_contents = {}
            if output_files and not result.error:
                for path in output_files:
                    try:
                        output_file_contents[path] = read_output_file_bytes(sandbox, path)
                        logger.info(f"Read output file from sandbox: {path}")
                    except Exception as e:
                        logger.error(f"Failed to read output file {path}: {str(e)}")
                        output_file_contents[path] = None
            elif output_files:
                output_file_contents = {path: None for path in output_files}

            return {
                "stdout": result.logs.stdout,
                "stderr": result.logs.stderr,
                "error": result.error,
                "results": result.results,
                "output_files": output_file_contents
            }
        finally:
            sandbox.kill()

    except Exception as e:
        logger.error(f"Sandbox execution failed: {str(e)}")
        return {
            "stdout": [],
            "stderr": [],
            "error": str(e),
            "results": [],
            "output_files": {}
        }
