# TODO: Migrate to TOML based builds
from setuptools import find_packages, setup

with open("requirements.txt", "r", encoding="utf-8") as file:
    requires = []
    for line in file:
        req = line.split("#", 1)[0].strip()
        if req and not req.startswith("--"):
            requires.append(req)

setup(
    name="api.jedwal.co",
    version="0.1",
    packages=find_packages(exclude=["tests", "data"]),
    install_requires=requires,
)
