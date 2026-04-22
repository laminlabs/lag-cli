from lag_cli.agent import _looks_like_wrapper_runner


def test_detects_subprocess_wrapper_runner() -> None:
    code = """
import subprocess
result = subprocess.run(["python", "write_hello.py"], capture_output=True, text=True)
print(result.stdout)
"""
    assert _looks_like_wrapper_runner(code, ["write_hello.py"])


def test_allows_regular_task_script() -> None:
    code = """
import lamindb as ln
with open("hello.txt", "w") as f:
    f.write("Hello agent!")
ln.Artifact("hello.txt").save()
"""
    assert not _looks_like_wrapper_runner(code, [])
